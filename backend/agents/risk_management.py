"""Risk Management Agent — position sizing, VaR, drawdown control, kill switch."""
from __future__ import annotations

from typing import List

from loguru import logger

from config import get_settings
from core.state import PositionSize, RiskMetrics, TradingSignal, TradingState
from risk.drawdown_controller import DrawdownController
from risk.kill_switch import KillSwitch
from risk.position_sizer import PositionSizer
from services.database import DatabaseService

settings = get_settings()


async def risk_management_node(state: TradingState) -> TradingState:
    """Validate signals, size positions, enforce drawdown limits."""
    logger.info(f"[RiskManagement] cycle={state.cycle_id}")

    db = DatabaseService()
    # KillSwitch is Redis-backed — persists across restarts and workers
    kill_switch = KillSwitch(
        redis_url=settings.redis_url,
        max_drawdown=settings.max_portfolio_drawdown,
    )
    position_sizer = PositionSizer(
        risk_per_trade=settings.risk_per_trade,
        base_currency=settings.base_currency,
    )
    drawdown_ctrl = DrawdownController()

    try:
        # ── Load current portfolio state ───────────────────────────
        portfolio = await db.get_portfolio_snapshot()
        if portfolio:
            state.portfolio = portfolio

        equity = portfolio.total_equity if portfolio else settings.initial_capital
        peak_equity = portfolio.peak_equity if portfolio else equity
        current_drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0

        # ── Kill switch check (Redis-persistent) ──────────────────
        if await kill_switch.should_trigger(current_drawdown):
            logger.warning(
                f"[RiskManagement] Kill switch triggered! drawdown={current_drawdown:.2%}"
            )
            state.kill_switch = True
            state.skip_execution = True
            state.agent_messages.append(
                f"[RiskManagement] KILL SWITCH: drawdown={current_drawdown:.2%} "
                f"exceeds limit={settings.max_portfolio_drawdown:.2%}"
            )
            return state

        # ── Compute risk metrics ───────────────────────────────────
        trade_history = await db.get_recent_trades(limit=100)
        risk_metrics = drawdown_ctrl.compute_metrics(
            trade_history=trade_history,
            equity=equity,
            peak_equity=peak_equity,
        )
        risk_metrics.current_drawdown = current_drawdown
        state.risk_metrics = risk_metrics

        # ── Size and approve positions ─────────────────────────────
        open_position_count = len(portfolio.open_positions) if portfolio else 0
        available_slots = settings.max_open_positions - open_position_count
        approved: List[PositionSize] = []
        rejected: List[PositionSize] = []

        for signal in state.filtered_signals:
            if len(approved) >= available_slots:
                ps = PositionSize(
                    symbol=signal.symbol,
                    signal=signal,
                    size_usd=0,
                    size_units=0,
                    risk_amount=0,
                    risk_pct=0,
                    approved=False,
                    rejection_reason="max_positions_reached",
                )
                rejected.append(ps)
                continue

            # Skip if already holding position in this symbol
            if portfolio and signal.symbol in portfolio.open_positions:
                ps = PositionSize(
                    symbol=signal.symbol,
                    signal=signal,
                    size_usd=0,
                    size_units=0,
                    risk_amount=0,
                    risk_pct=0,
                    approved=False,
                    rejection_reason="position_already_open",
                )
                rejected.append(ps)
                continue

            ps = position_sizer.calculate(
                signal=signal,
                equity=equity,
                current_price=signal.entry_price,
            )

            validation = _validate_position(ps, risk_metrics, equity)
            if validation["approved"]:
                ps.approved = True
                approved.append(ps)
                logger.info(
                    f"[RiskManagement] APPROVED {signal.symbol} "
                    f"size_usd={ps.size_usd:.2f} risk={ps.risk_pct:.2%}"
                )
            else:
                ps.approved = False
                ps.rejection_reason = validation["reason"]
                rejected.append(ps)
                logger.debug(
                    f"[RiskManagement] REJECTED {signal.symbol}: {validation['reason']}"
                )

        state.approved_positions = approved
        state.rejected_positions = rejected
        state.agent_messages.append(
            f"[RiskManagement] approved={len(approved)} rejected={len(rejected)} "
            f"drawdown={current_drawdown:.2%} VaR_1d={risk_metrics.portfolio_var_1d:.2%}"
        )

    except Exception as e:
        logger.error(f"[RiskManagement] error: {e}", exc_info=True)
        state.errors.append(f"risk_management: {str(e)}")
    finally:
        await kill_switch.close()

    return state


def _validate_position(
    ps: PositionSize,
    risk_metrics: RiskMetrics,
    equity: float,
) -> dict:
    """Check R:R ratio, max single risk, and portfolio risk budget."""
    signal = ps.signal

    # Minimum risk/reward ratio
    if signal.entry_price <= 0 or signal.stop_loss <= 0:
        return {"approved": False, "reason": "invalid_price_levels"}

    risk_pips = abs(signal.entry_price - signal.stop_loss)
    reward_pips = abs(signal.take_profit - signal.entry_price)
    rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0

    if rr_ratio < 1.5:
        return {"approved": False, "reason": f"rr_ratio_too_low={rr_ratio:.2f}"}

    # Minimum confidence
    if signal.confidence < 0.55:
        return {"approved": False, "reason": f"low_confidence={signal.confidence:.2f}"}

    # Single trade risk cap
    if ps.risk_pct > settings.risk_per_trade * 2:
        return {"approved": False, "reason": f"risk_too_large={ps.risk_pct:.2%}"}

    # VaR-adjusted portfolio risk
    if risk_metrics.portfolio_var_1d > 0.05:
        return {"approved": False, "reason": f"portfolio_var_too_high={risk_metrics.portfolio_var_1d:.2%}"}

    return {"approved": True, "reason": ""}
