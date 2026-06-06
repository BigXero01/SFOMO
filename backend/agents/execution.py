"""Execution Agent — smart order routing, TWAP/VWAP, slippage minimization."""
from __future__ import annotations

import asyncio
import random
import uuid
from typing import Any, Dict, List

from loguru import logger

from config import get_settings
from core.state import ExecutedOrder, OrderSide, PositionSize, TradingState
from services.database import DatabaseService
from services.exchange import ExchangeService

settings = get_settings()

TWAP_SLICES = 3                # split large orders into N time-weighted slices
TWAP_INTERVAL_BASE_SEC = 4     # base interval between slices
TWAP_INTERVAL_JITTER_SEC = 3   # random ±jitter to resist front-running detection
MAX_SLIPPAGE_PCT = 0.003        # 0.3% max acceptable slippage


async def execution_node(state: TradingState) -> TradingState:
    """Route and execute approved positions with slippage protection."""
    logger.info(
        f"[Execution] cycle={state.cycle_id} "
        f"positions={len(state.approved_positions)}"
    )

    if state.skip_execution or state.kill_switch:
        state.agent_messages.append("[Execution] Skipped — kill switch or no approved positions")
        return state

    exchange = ExchangeService()
    db = DatabaseService()
    executed: List[ExecutedOrder] = []
    failed: List[Dict[str, Any]] = []

    try:
        for position in state.approved_positions:
            try:
                order = await _execute_position(exchange, position, state)
                if order:
                    executed.append(order)
                    logger.info(
                        f"[Execution] FILLED {order.symbol} "
                        f"side={order.side.value} price={order.price:.4f} "
                        f"size={order.size:.6f} slippage={order.slippage_pct:.4%}"
                    )
                    await db.record_audit_log(
                        action="order_filled",
                        cycle_id=state.cycle_id,
                        symbol=order.symbol,
                        side=order.side.value,
                        size=order.size,
                        price=order.price,
                        order_id=order.order_id,
                        status="filled",
                    )
            except Exception as e:
                logger.error(f"[Execution] order failed {position.symbol}: {e}", exc_info=True)
                failed.append({"symbol": position.symbol, "error": str(e)})
                await db.record_audit_log(
                    action="order_failed",
                    cycle_id=state.cycle_id,
                    symbol=position.symbol,
                    status="failed",
                    detail=str(e),
                )

    finally:
        await exchange.close()

    state.executed_orders = executed
    state.failed_orders = failed
    state.agent_messages.append(
        f"[Execution] filled={len(executed)} failed={len(failed)}"
    )

    return state


async def _execute_position(
    exchange: ExchangeService,
    position: PositionSize,
    state: TradingState,
) -> ExecutedOrder | None:
    """Execute a single position using smart order routing."""
    signal = position.signal
    side = OrderSide.BUY if signal.direction.value == "long" else OrderSide.SELL

    # Check order-book liquidity — block the order if depth is insufficient
    ob = state.order_books.get(signal.symbol)
    if ob:
        liquidity_ok = _check_liquidity(ob, side, position.size_usd)
        if not liquidity_ok:
            logger.warning(
                f"[Execution] insufficient liquidity for {signal.symbol} "
                f"size_usd={position.size_usd:.2f} — skipping"
            )
            return None

    # Live balance check — confirm we have enough free balance before submitting
    try:
        balance = await exchange.fetch_balance()
        quote_currency = signal.symbol.split("/")[-1] if "/" in signal.symbol else settings.base_currency
        available = float(balance.get("free", {}).get(quote_currency, 0) or 0)
        if available < position.size_usd * 1.01:  # 1% buffer for fees
            logger.warning(
                f"[Execution] insufficient balance for {signal.symbol}: "
                f"need {position.size_usd:.2f} {quote_currency}, "
                f"have {available:.2f}"
            )
            return None
    except Exception as e:
        logger.warning(f"[Execution] balance check failed for {signal.symbol}: {e}")
        return None

    use_twap = position.size_usd > 1000 and TWAP_SLICES > 1

    if use_twap:
        return await _twap_execute(exchange, signal.symbol, side, position, signal.entry_price)
    else:
        return await _market_execute(exchange, signal.symbol, side, position, signal.entry_price)


async def _market_execute(
    exchange: ExchangeService,
    symbol: str,
    side: OrderSide,
    position: PositionSize,
    expected_price: float,
) -> ExecutedOrder | None:
    """Simple market order execution with slippage check."""
    client_order_id = f"sfomo-{uuid.uuid4().hex[:16]}"
    order_result = await exchange.create_order(
        symbol=symbol,
        order_type="market",
        side=side.value,
        amount=position.size_units,
        params={"clientOrderId": client_order_id},
    )

    filled_price = order_result.get("average", order_result.get("price", expected_price))
    slippage = abs(filled_price - expected_price) / expected_price if expected_price > 0 else 0

    if slippage > MAX_SLIPPAGE_PCT:
        logger.warning(
            f"[Execution] High slippage {symbol}: {slippage:.4%} > {MAX_SLIPPAGE_PCT:.4%}"
        )

    return ExecutedOrder(
        symbol=symbol,
        side=side,
        size=position.size_units,
        price=filled_price,
        order_id=order_result.get("id", client_order_id),
        exchange=settings.exchange_id,
        fees=order_result.get("fee", {}).get("cost", 0.0),
        slippage_pct=slippage,
    )


async def _twap_execute(
    exchange: ExchangeService,
    symbol: str,
    side: OrderSide,
    position: PositionSize,
    expected_price: float,
) -> ExecutedOrder | None:
    """TWAP execution — splits order into randomised time-weighted slices."""
    from risk.kill_switch import KillSwitch
    kill_switch = KillSwitch(max_drawdown=settings.max_portfolio_drawdown)

    slice_size = position.size_units / TWAP_SLICES
    total_filled = 0.0
    total_cost = 0.0
    total_fees = 0.0
    all_order_ids: List[str] = []

    for i in range(TWAP_SLICES):
        # Re-check kill switch between slices — it may have been triggered
        # by another concurrent process between our slices.
        if await kill_switch.is_triggered():
            logger.warning(
                f"[Execution] Kill switch triggered mid-TWAP for {symbol} "
                f"after {i} of {TWAP_SLICES} slices"
            )
            break

        client_order_id = f"sfomo-twap-{uuid.uuid4().hex[:12]}"
        try:
            order_result = await exchange.create_order(
                symbol=symbol,
                order_type="market",
                side=side.value,
                amount=slice_size,
                params={"clientOrderId": client_order_id},
            )
            price = order_result.get("average", expected_price)
            total_filled += slice_size
            total_cost += slice_size * price
            total_fees += order_result.get("fee", {}).get("cost", 0.0)
            all_order_ids.append(order_result.get("id", client_order_id))

            if i < TWAP_SLICES - 1:
                jitter = random.uniform(-TWAP_INTERVAL_JITTER_SEC, TWAP_INTERVAL_JITTER_SEC)
                await asyncio.sleep(max(1.0, TWAP_INTERVAL_BASE_SEC + jitter))

        except Exception as e:
            logger.warning(f"[Execution] TWAP slice {i+1} failed: {e}")

    if total_filled == 0:
        return None

    avg_price = total_cost / total_filled
    slippage = abs(avg_price - expected_price) / expected_price if expected_price > 0 else 0
    # Concatenate all slice order IDs separated by "|"
    combined_order_id = "|".join(all_order_ids) if all_order_ids else ""

    return ExecutedOrder(
        symbol=symbol,
        side=side,
        size=total_filled,
        price=avg_price,
        order_id=combined_order_id,
        exchange=settings.exchange_id,
        fees=total_fees,
        slippage_pct=slippage,
    )


def _check_liquidity(order_book: Dict[str, Any], side: OrderSide, size_usd: float) -> bool:
    """Verify sufficient order book depth for the order size."""
    key = "asks" if side == OrderSide.BUY else "bids"
    levels = order_book.get(key, [])[:10]
    available = sum(price * qty for price, qty in levels)
    return available >= size_usd * 0.5
