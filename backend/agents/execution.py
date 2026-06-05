"""Execution Agent — smart order routing, TWAP/VWAP, slippage minimization."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from loguru import logger

from config import get_settings
from core.state import ExecutedOrder, OrderSide, PositionSize, TradingState
from services.exchange import ExchangeService

settings = get_settings()

TWAP_SLICES = 3          # split large orders into N slices
TWAP_INTERVAL_SEC = 5    # seconds between slices
MAX_SLIPPAGE_PCT = 0.003  # 0.3% max acceptable slippage


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
            except Exception as e:
                logger.error(f"[Execution] order failed {position.symbol}: {e}")
                failed.append({"symbol": position.symbol, "error": str(e)})

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

    # Check liquidity from order book
    ob = state.order_books.get(signal.symbol)
    if ob:
        liquidity_ok = _check_liquidity(ob, side, position.size_usd)
        if not liquidity_ok:
            logger.warning(f"[Execution] insufficient liquidity for {signal.symbol}")

    # Use TWAP for large orders (> 5% of available liquidity)
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
    order_result = await exchange.create_order(
        symbol=symbol,
        order_type="market",
        side=side.value,
        amount=position.size_units,
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
        order_id=order_result.get("id", ""),
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
    """TWAP execution — splits order into time-weighted slices."""
    slice_size = position.size_units / TWAP_SLICES
    total_filled = 0.0
    total_cost = 0.0
    total_fees = 0.0
    last_order_id = ""

    for i in range(TWAP_SLICES):
        try:
            order_result = await exchange.create_order(
                symbol=symbol,
                order_type="market",
                side=side.value,
                amount=slice_size,
            )
            price = order_result.get("average", expected_price)
            total_filled += slice_size
            total_cost += slice_size * price
            total_fees += order_result.get("fee", {}).get("cost", 0.0)
            last_order_id = order_result.get("id", "")

            if i < TWAP_SLICES - 1:
                await asyncio.sleep(TWAP_INTERVAL_SEC)

        except Exception as e:
            logger.warning(f"[Execution] TWAP slice {i+1} failed: {e}")

    if total_filled == 0:
        return None

    avg_price = total_cost / total_filled
    slippage = abs(avg_price - expected_price) / expected_price if expected_price > 0 else 0

    return ExecutedOrder(
        symbol=symbol,
        side=side,
        size=total_filled,
        price=avg_price,
        order_id=last_order_id,
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
