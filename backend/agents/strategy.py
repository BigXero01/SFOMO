"""Strategy Agent — runs all strategies, aggregates signals via regime weighting."""
from __future__ import annotations

import json
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from loguru import logger

from config import get_settings
from core.state import MarketRegime, SignalDirection, SignalStrength, TradingSignal, TradingState
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum_breakout import MomentumBreakoutStrategy
from strategies.portfolio_rotation import PortfolioRotationStrategy
from strategies.trend_following import TrendFollowingStrategy
from strategies.volatility_arb import VolatilityArbStrategy

settings = get_settings()

_llm = ChatOpenAI(
    model=settings.openai_model,
    temperature=0.1,
    api_key=settings.openai_api_key,
)

# Regime → strategy weight overrides (multiplicative adjustment)
REGIME_ADJUSTMENTS: Dict[MarketRegime, Dict[str, float]] = {
    MarketRegime.BULL_TREND: {
        "trend_following": 1.5,
        "momentum_breakout": 1.3,
        "mean_reversion": 0.5,
        "volatility_arb": 0.7,
        "portfolio_rotation": 1.0,
    },
    MarketRegime.BEAR_TREND: {
        "trend_following": 1.3,
        "momentum_breakout": 0.8,
        "mean_reversion": 0.6,
        "volatility_arb": 1.2,
        "portfolio_rotation": 0.7,
    },
    MarketRegime.RANGING: {
        "trend_following": 0.6,
        "momentum_breakout": 0.7,
        "mean_reversion": 1.5,
        "volatility_arb": 1.2,
        "portfolio_rotation": 1.0,
    },
    MarketRegime.HIGH_VOLATILITY: {
        "trend_following": 0.8,
        "momentum_breakout": 1.2,
        "mean_reversion": 0.4,
        "volatility_arb": 1.8,
        "portfolio_rotation": 0.6,
    },
    MarketRegime.LOW_VOLATILITY: {
        "trend_following": 1.0,
        "momentum_breakout": 0.6,
        "mean_reversion": 1.4,
        "volatility_arb": 0.5,
        "portfolio_rotation": 1.3,
    },
}

FILTER_PROMPT = """You are an elite crypto trading strategist.
Review these trading signals and filter for only high-conviction setups.
Criteria:
- Minimum confidence 0.65 for STRONG, 0.55 for MODERATE
- Signals must align with the current market regime: {regime}
- Reject signals where entry risk/reward < 1.5
- Max {max_positions} signals total, prioritize highest conviction

Signals (JSON):
{signals}

Return a JSON array of approved signal objects (same schema, no markdown).
If none pass, return []."""


def _apply_regime_weights(
    base_weights: Dict[str, float],
    regime: MarketRegime,
) -> Dict[str, float]:
    adjustments = REGIME_ADJUSTMENTS.get(regime, {})
    adjusted = {k: v * adjustments.get(k, 1.0) for k, v in base_weights.items()}
    total = sum(adjusted.values())
    return {k: v / total for k, v in adjusted.items()} if total > 0 else base_weights


async def strategy_node(state: TradingState) -> TradingState:
    """Run all strategies and filter signals via LLM."""
    logger.info(f"[Strategy] cycle={state.cycle_id} regime={state.market_regime.value}")

    regime_weights = _apply_regime_weights(state.strategy_weights, state.market_regime)
    state.strategy_weights = regime_weights

    strategies = {
        "trend_following": TrendFollowingStrategy(weight=regime_weights["trend_following"]),
        "momentum_breakout": MomentumBreakoutStrategy(weight=regime_weights["momentum_breakout"]),
        "mean_reversion": MeanReversionStrategy(weight=regime_weights["mean_reversion"]),
        "volatility_arb": VolatilityArbStrategy(weight=regime_weights["volatility_arb"]),
        "portfolio_rotation": PortfolioRotationStrategy(weight=regime_weights["portfolio_rotation"]),
    }

    raw_signals: List[TradingSignal] = []
    for name, strat in strategies.items():
        try:
            signals = await strat.generate_signals(
                candles=state.candles,
                order_books=state.order_books,
                market_structure=state.market_structure,
                funding_rates=state.funding_rates,
            )
            raw_signals.extend(signals)
            logger.debug(f"[Strategy] {name} generated {len(signals)} signals")
        except Exception as e:
            logger.warning(f"[Strategy] {name} error: {e}")
            state.errors.append(f"strategy.{name}: {str(e)}")

    state.raw_signals = raw_signals

    if not raw_signals:
        state.agent_messages.append("[Strategy] No signals generated this cycle")
        return state

    # LLM signal filtering
    try:
        signals_json = json.dumps(
            [s.model_dump(mode="json") for s in raw_signals], default=str
        )
        messages = [
            SystemMessage(
                content=FILTER_PROMPT.format(
                    regime=state.market_regime.value,
                    max_positions=settings.max_open_positions,
                    signals=signals_json,
                )
            ),
            HumanMessage(content="Filter and rank these signals."),
        ]
        response = await _llm.ainvoke(messages)
        filtered_data = json.loads(response.content)
        filtered_signals = [TradingSignal(**s) for s in filtered_data]
        state.filtered_signals = filtered_signals

        state.agent_messages.append(
            f"[Strategy] raw={len(raw_signals)} filtered={len(filtered_signals)} "
            f"regime_weights={regime_weights}"
        )
    except Exception as e:
        logger.error(f"[Strategy] LLM filter error: {e}")
        # Fallback: use top signals by confidence
        state.filtered_signals = sorted(raw_signals, key=lambda s: s.confidence, reverse=True)[
            : settings.max_open_positions
        ]

    return state
