"""Portfolio Manager Agent — allocation, compounding engine, rebalancing."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from loguru import logger
from pypfopt import EfficientFrontier, expected_returns, risk_models

from config import get_settings
from core.state import PortfolioSnapshot, TradingState
from services.database import DatabaseService

settings = get_settings()

REBALANCE_THRESHOLD = 0.05   # rebalance if any position drifts > 5% from target
COMPOUNDING_REINVEST_PCT = 0.80  # reinvest 80% of profits


async def portfolio_manager_node(state: TradingState) -> TradingState:
    """Update portfolio, record trades, compute compounding allocation."""
    logger.info(f"[PortfolioManager] cycle={state.cycle_id}")

    db = DatabaseService()

    try:
        # ── Record executed orders ─────────────────────────────────
        for order in state.executed_orders:
            await db.record_trade(order, state.cycle_id)

        # ── Refresh portfolio snapshot ─────────────────────────────
        prev_snapshot = await db.get_portfolio_snapshot()
        prev_realized_pnl = prev_snapshot.realized_pnl if prev_snapshot else 0.0

        portfolio = prev_snapshot or PortfolioSnapshot(
            total_equity=settings.initial_capital,
            cash=settings.initial_capital,
            positions_value=0.0,
            peak_equity=settings.initial_capital,
        )

        # Update peak equity and persist it so restarts don't lose the high watermark
        if portfolio.total_equity > portfolio.peak_equity:
            portfolio.peak_equity = portfolio.total_equity

        portfolio.current_drawdown = (
            (portfolio.peak_equity - portfolio.total_equity) / portfolio.peak_equity
            if portfolio.peak_equity > 0 else 0.0
        )

        # Persist the updated snapshot (including the potentially new peak)
        await db.save_portfolio_snapshot(portfolio)

        state.portfolio = portfolio

        # ── Compounding engine — use cycle-delta PnL, not cumulative ──────────
        # Using cumulative realized_pnl would reinvest all-time profits each cycle.
        cycle_pnl_delta = portfolio.realized_pnl - prev_realized_pnl
        if cycle_pnl_delta > 0:
            reinvest = cycle_pnl_delta * COMPOUNDING_REINVEST_PCT
            allocation = _compute_compounding_allocation(
                reinvest_amount=reinvest,
                strategy_weights=state.strategy_weights,
            )
            state.compounding_allocation = allocation
            logger.info(
                f"[PortfolioManager] compounding reinvest={reinvest:.2f} "
                f"allocation={allocation}"
            )

        # ── Rebalance check ────────────────────────────────────────
        if portfolio.open_positions:
            state.rebalance_needed = _check_rebalance_needed(
                portfolio=portfolio,
                target_weights=state.strategy_weights,
            )

        # ── Performance attribution ────────────────────────────────
        recent_trades = await db.get_recent_trades(limit=50)
        state.performance_attribution = _compute_attribution(recent_trades)

        state.agent_messages.append(
            f"[PortfolioManager] equity={portfolio.total_equity:.2f} "
            f"cash={portfolio.cash:.2f} "
            f"drawdown={portfolio.current_drawdown:.2%} "
            f"rebalance_needed={state.rebalance_needed}"
        )

    except Exception as e:
        logger.error(f"[PortfolioManager] error: {e}")
        state.errors.append(f"portfolio_manager: {str(e)}")

    return state


def _compute_compounding_allocation(
    reinvest_amount: float,
    strategy_weights: Dict[str, float],
) -> Dict[str, float]:
    """Distribute reinvestment proportionally to strategy weights."""
    return {
        strategy: reinvest_amount * weight
        for strategy, weight in strategy_weights.items()
    }


def _check_rebalance_needed(
    portfolio: PortfolioSnapshot,
    target_weights: Dict[str, float],
) -> bool:
    """Check if any position has drifted beyond rebalance threshold."""
    if not portfolio.open_positions or portfolio.total_equity <= 0:
        return False

    for symbol, position_data in portfolio.open_positions.items():
        position_value = position_data.get("value", 0)
        current_weight = position_value / portfolio.total_equity
        # Map symbol to strategy — simplified heuristic
        strategy_weight = sum(target_weights.values()) / len(target_weights)
        if abs(current_weight - strategy_weight) > REBALANCE_THRESHOLD:
            return True

    return False


def _compute_attribution(trades: List[Dict]) -> Dict[str, float]:
    """Compute P&L attribution by strategy."""
    attribution: Dict[str, float] = {}
    for trade in trades:
        strategy = trade.get("strategy", "unknown")
        pnl = trade.get("pnl", 0.0)
        attribution[strategy] = attribution.get(strategy, 0.0) + pnl
    return attribution
