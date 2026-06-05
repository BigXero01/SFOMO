"""Learning Agent — strategy evaluation, regime detection, RL feedback loop."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from loguru import logger

from config import get_settings
from core.state import MarketRegime, TradingState
from services.database import DatabaseService
from services.vector_store import VectorStoreService

settings = get_settings()

_llm = ChatOpenAI(
    model=settings.openai_model,
    temperature=0.2,
    api_key=settings.openai_api_key,
)

LEARNING_PROMPT = """You are an AI trading system learning agent.
Analyze the completed trading cycle and provide feedback to improve future performance.

Current cycle performance:
- Executed trades: {executed_count}
- Rejected signals: {rejected_count}
- Market regime: {regime}
- Current drawdown: {drawdown:.2%}
- Strategy weights used: {weights}
- P&L attribution: {attribution}

Recent trade outcomes (last 20):
{recent_trades}

Regime history (last 10 cycles):
{regime_history}

Provide JSON response:
{
  "weight_adjustments": {"strategy_name": <float delta -0.1 to 0.1>},
  "regime_confidence": <float 0-1>,
  "regime_persistence": <int estimated cycles>,
  "lessons": ["<key learnings>"],
  "parameter_suggestions": {"param": <value>},
  "overall_assessment": "<brief assessment>"
}
Return only valid JSON."""


async def learning_node(state: TradingState) -> TradingState:
    """Evaluate cycle, update strategy weights, store learnings in vector DB."""
    logger.info(f"[Learning] cycle={state.cycle_id}")

    db = DatabaseService()
    vector_store = VectorStoreService()

    try:
        # ── Load recent performance data ───────────────────────────
        recent_trades = await db.get_recent_trades(limit=20)
        regime_history = await db.get_regime_history(limit=10)

        state.closed_trades = recent_trades
        state.regime_history = regime_history

        # ── Compute strategy performance metrics ───────────────────
        strategy_perf = _compute_strategy_metrics(recent_trades)
        state.strategy_performance = strategy_perf

        # ── LLM-driven learning feedback ───────────────────────────
        current_drawdown = (
            state.portfolio.current_drawdown if state.portfolio else 0.0
        )

        messages = [
            SystemMessage(content=LEARNING_PROMPT.format(
                executed_count=len(state.executed_orders),
                rejected_count=len(state.rejected_positions),
                regime=state.market_regime.value,
                drawdown=current_drawdown,
                weights=json.dumps(state.strategy_weights),
                attribution=json.dumps(state.performance_attribution),
                recent_trades=json.dumps(recent_trades[:20], default=str),
                regime_history=json.dumps(regime_history[:10], default=str),
            )),
            HumanMessage(content="Provide learning feedback for this cycle."),
        ]

        response = await _llm.ainvoke(messages)
        feedback = json.loads(response.content)
        state.rl_feedback = feedback

        # ── Apply weight adjustments ───────────────────────────────
        weight_adjustments: Dict[str, float] = feedback.get("weight_adjustments", {})
        if weight_adjustments:
            updated_weights = _apply_weight_adjustments(
                current_weights=state.strategy_weights,
                adjustments=weight_adjustments,
            )
            state.strategy_weights = updated_weights
            await db.save_strategy_weights(updated_weights)

        # ── Persist regime data ────────────────────────────────────
        await db.record_regime(
            regime=state.market_regime.value,
            cycle_id=state.cycle_id,
            confidence=feedback.get("regime_confidence", 0.5),
        )

        # ── Store cycle summary in vector DB ───────────────────────
        cycle_summary = _build_cycle_summary(state, feedback)
        await vector_store.store_cycle_memory(
            cycle_id=state.cycle_id,
            content=cycle_summary,
            metadata={
                "regime": state.market_regime.value,
                "drawdown": current_drawdown,
                "executed": len(state.executed_orders),
                "cycle_id": state.cycle_id,
            },
        )

        logger.info(
            f"[Learning] lessons={len(feedback.get('lessons', []))} "
            f"weight_adjustments={weight_adjustments} "
            f"assessment={feedback.get('overall_assessment', '')[:80]}"
        )

        state.agent_messages.append(
            f"[Learning] {feedback.get('overall_assessment', 'Cycle complete')}"
        )

    except Exception as e:
        logger.error(f"[Learning] error: {e}")
        state.errors.append(f"learning: {str(e)}")

    return state


def _compute_strategy_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate win rate, avg P&L, and Sharpe per strategy."""
    metrics: Dict[str, Dict[str, Any]] = {}
    for trade in trades:
        strat = trade.get("strategy", "unknown")
        pnl = trade.get("pnl", 0.0)
        if strat not in metrics:
            metrics[strat] = {"trades": 0, "wins": 0, "total_pnl": 0.0, "pnls": []}
        metrics[strat]["trades"] += 1
        metrics[strat]["total_pnl"] += pnl
        metrics[strat]["pnls"].append(pnl)
        if pnl > 0:
            metrics[strat]["wins"] += 1

    for strat, m in metrics.items():
        m["win_rate"] = m["wins"] / m["trades"] if m["trades"] > 0 else 0.0
        m["avg_pnl"] = m["total_pnl"] / m["trades"] if m["trades"] > 0 else 0.0
        pnls = m["pnls"]
        if len(pnls) > 1:
            import statistics
            std = statistics.stdev(pnls)
            m["sharpe"] = (m["avg_pnl"] / std) if std > 0 else 0.0
        else:
            m["sharpe"] = 0.0

    return metrics


def _apply_weight_adjustments(
    current_weights: Dict[str, float],
    adjustments: Dict[str, float],
    min_weight: float = 0.05,
    max_weight: float = 0.50,
) -> Dict[str, float]:
    """Apply delta adjustments and re-normalize weights."""
    updated = {
        k: max(min_weight, min(max_weight, v + adjustments.get(k, 0.0)))
        for k, v in current_weights.items()
    }
    total = sum(updated.values())
    return {k: v / total for k, v in updated.items()} if total > 0 else current_weights


def _build_cycle_summary(state: TradingState, feedback: Dict[str, Any]) -> str:
    return (
        f"Cycle {state.cycle_id} | "
        f"Regime: {state.market_regime.value} | "
        f"Signals: {len(state.raw_signals)} raw, {len(state.filtered_signals)} filtered | "
        f"Executed: {len(state.executed_orders)} orders | "
        f"Drawdown: {state.portfolio.current_drawdown:.2%} | " if state.portfolio else "" +
        f"Lessons: {', '.join(feedback.get('lessons', [])[:3])}"
    )
