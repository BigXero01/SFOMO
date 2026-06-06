"""Terminal command handlers — every command streams output line-by-line."""
from __future__ import annotations

import asyncio
import shlex
from datetime import datetime, timezone
from typing import AsyncIterator, Callable, Dict, List, Optional, Tuple

from loguru import logger

from config import get_settings

settings = get_settings()

# ── Output line type ─────────────────────────────────────────────────────────

Line = Tuple[str, str]   # (text, style)

# Styles: normal | success | error | warn | info | gold | muted | dim | code | header


def _line(text: str, style: str = "normal") -> Line:
    return (text, style)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _table(
    headers: List[str],
    rows: List[List[str]],
    col_styles: Optional[List[str]] = None,
) -> List[Line]:
    """Render a simple fixed-width text table."""
    if not rows:
        return [_line("  (no data)", "muted")]

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    sep = "  ".join("─" * w for w in widths)
    header_row = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    lines: List[Line] = [
        _line(f"  {header_row}", "gold"),
        _line(f"  {sep}", "muted"),
    ]
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cells.append(str(cell).ljust(widths[i] if i < len(widths) else 0))
        row_text = "  ".join(cells)
        style = col_styles[0] if col_styles else "normal"
        lines.append(_line(f"  {row_text}", style))
    return lines


async def _yield_lines(lines: List[Line]) -> AsyncIterator[Line]:
    for line in lines:
        yield line
        await asyncio.sleep(0)


# ── Banner & Help ─────────────────────────────────────────────────────────────

BANNER = [
    ("", "normal"),
    ("  ███████╗███████╗ ██████╗ ███╗   ███╗ ██████╗ ", "gold"),
    ("  ██╔════╝██╔════╝██╔═══██╗████╗ ████║██╔═══██╗", "gold"),
    ("  ███████╗█████╗  ██║   ██║██╔████╔██║██║   ██║", "gold"),
    ("  ╚════██║██╔══╝  ██║   ██║██║╚██╔╝██║██║   ██║", "gold"),
    ("  ███████║██║     ╚██████╔╝██║ ╚═╝ ██║╚██████╔╝", "gold"),
    ("  ╚══════╝╚═╝      ╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ", "gold"),
    ("", "normal"),
    ("  AI Agent Trading System  ·  Production Terminal", "muted"),
    ("  Type  help  to list all commands", "dim"),
    ("", "normal"),
]

COMMANDS_HELP = [
    ("status",                    "System health, scheduler, kill switch"),
    ("cycle [SYM [SYM..]] [TF]", "Run one trading cycle with live streaming"),
    ("portfolio",                 "Current equity, positions, drawdown"),
    ("signals",                   "Filtered signals from last cycle"),
    ("trades [N]",                "Recent N trade executions (default 20)"),
    ("weights [STRATEGY VALUE]",  "Show or update a strategy weight"),
    ("regime",                    "Current market regime + history"),
    ("scheduler [start|stop|interval N]", "Manage the auto-cycle scheduler"),
    ("kill",                      "Manually trigger the kill switch"),
    ("reset-kill",                "Re-enable trading after kill switch"),
    ("backtest [SYM] [DAYS]",     "Run strategy backtest on historical data"),
    ("agents",                    "Show last cycle agent pipeline log"),
    ("logs [N]",                  "Tail last N agent messages (default 50)"),
    ("balances",                  "Show exchange coin balances"),
    ("deposit <CURRENCY> [NET]",  "Get on-chain deposit address"),
    ("withdraw <C> <AMT> <ADDR> [NET] [--confirm]", "Submit a withdrawal"),
    ("deposits [CURRENCY] [N]",   "Deposit history (default 20)"),
    ("withdrawals [CURRENCY] [N]","Withdrawal history (default 20)"),
    ("ping",                      "Latency + connectivity check"),
    ("version",                   "Version and build info"),
    ("clear",                     "Clear the terminal"),
    ("help",                      "Show this help"),
]


async def cmd_help(_args: List[str]) -> AsyncIterator[Line]:
    yield _line("", "normal")
    yield _line("  Available commands:", "gold")
    yield _line("", "normal")
    for cmd, desc in COMMANDS_HELP:
        pad = 36
        yield _line(f"  {cmd.ljust(pad)}{desc}", "normal")
    yield _line("", "normal")


# ── status ───────────────────────────────────────────────────────────────────

async def cmd_status(_args: List[str]) -> AsyncIterator[Line]:
    from core.scheduler import get_scheduler
    from risk.kill_switch import KillSwitch
    from services.database import AsyncSessionLocal
    from sqlalchemy import text

    sch = get_scheduler()
    st = sch.status()
    ks = KillSwitch(redis_url=settings.redis_url)

    # DB probe
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    ks_triggered = await ks.is_triggered()
    await ks.close()

    yield _line("", "normal")
    yield _line("  ─── System Status ───────────────────────────", "muted")
    yield _line(f"  Database       {'OK' if db_ok else 'ERROR'}", "success" if db_ok else "error")
    yield _line(f"  Kill Switch    {'⚠ TRIGGERED' if ks_triggered else 'OK'}", "error" if ks_triggered else "success")
    yield _line(f"  Exchange       {settings.exchange_id} ({'sandbox' if settings.exchange_sandbox else 'LIVE'})", "warn" if settings.exchange_sandbox else "success")
    yield _line(f"  Environment    {settings.app_env}", "info")
    yield _line("", "normal")
    yield _line("  ─── Scheduler ───────────────────────────────", "muted")
    yield _line(f"  Status         {'RUNNING' if st['running'] else 'STOPPED'}", "success" if st["running"] else "warn")
    yield _line(f"  Interval       {st['interval_secs']}s ({st['interval_secs']//60}m)", "normal")
    yield _line(f"  Cycles Run     {st['cycle_count']}", "info")
    if st["last_run"]:
        yield _line(f"  Last Run       {st['last_run'][:19]}Z", "normal")
    if st["secs_until_next"] is not None:
        m, s = divmod(st["secs_until_next"], 60)
        yield _line(f"  Next Run In    {m}m {s}s", "info")
    if st["last_error"]:
        yield _line(f"  Last Error     {st['last_error'][:80]}", "error")
    yield _line("", "normal")


# ── cycle ─────────────────────────────────────────────────────────────────────

AGENT_ORDER = [
    "market_intelligence",
    "strategy",
    "risk_management",
    "execution",
    "portfolio_manager",
    "learning",
]

AGENT_LABELS = {
    "market_intelligence": "Market Intelligence",
    "strategy":            "Strategy",
    "risk_management":     "Risk Management",
    "execution":           "Execution",
    "portfolio_manager":   "Portfolio Manager",
    "learning":            "Learning",
}


async def cmd_cycle(args: List[str]) -> AsyncIterator[Line]:
    import uuid
    from datetime import datetime
    from core.graph import graph
    from core.state import TradingState

    # Parse args: any arg matching X/Y is a symbol, last short arg is timeframe
    symbols: List[str] = []
    timeframe = settings.timeframe

    for arg in args:
        if "/" in arg:
            symbols.append(arg.upper())
        elif arg in {"1m","3m","5m","15m","30m","1h","2h","4h","6h","12h","1d","1w"}:
            timeframe = arg

    symbols = symbols or settings.trading_pairs

    cycle_id = str(uuid.uuid4())[:8]
    yield _line("", "normal")
    yield _line(f"  ─── Cycle {cycle_id} ─────────────────────────────", "muted")
    yield _line(f"  Symbols    {', '.join(symbols)}", "info")
    yield _line(f"  Timeframe  {timeframe}", "info")
    yield _line(f"  Started    {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC", "muted")
    yield _line("", "normal")

    initial = TradingState(
        cycle_id=cycle_id,
        timestamp=datetime.utcnow(),
        symbols=symbols,
        timeframe=timeframe,
        strategy_weights={
            "trend_following":    settings.weight_trend_following,
            "momentum_breakout":  settings.weight_momentum_breakout,
            "mean_reversion":     settings.weight_mean_reversion,
            "volatility_arb":     settings.weight_volatility_arb,
            "portfolio_rotation": settings.weight_portfolio_rotation,
        },
    )

    completed: List[str] = []
    final_state: Optional[TradingState] = None
    t0 = asyncio.get_event_loop().time()

    try:
        async for event in graph.astream(initial):
            node = next(iter(event))
            state_data = event[node]
            elapsed = asyncio.get_event_loop().time() - t0
            completed.append(node)
            label = AGENT_LABELS.get(node, node)

            # Build pipeline progress bar
            bar = ""
            for a in AGENT_ORDER:
                if a in completed:
                    bar += "█"
                elif a == node:
                    bar += "░"
                else:
                    bar += "·"

            yield _line(
                f"  [{bar}] {label:<22} +{elapsed:.1f}s",
                "success",
            )

            # Per-agent detail lines
            if node == "market_intelligence":
                regime = state_data.get("market_regime", "")
                if isinstance(regime, str):
                    yield _line(f"       Regime: {regime}", "info")
                elif hasattr(regime, "value"):
                    yield _line(f"       Regime: {regime.value}", "info")

            elif node == "strategy":
                raw = len(state_data.get("raw_signals", []))
                filt = len(state_data.get("filtered_signals", []))
                yield _line(f"       Signals: {raw} raw → {filt} filtered", "info")

            elif node == "risk_management":
                approved = len(state_data.get("approved_positions", []))
                rejected = len(state_data.get("rejected_positions", []))
                ks = state_data.get("kill_switch", False)
                if ks:
                    yield _line("       ⚠ KILL SWITCH TRIGGERED", "error")
                else:
                    yield _line(f"       Positions: {approved} approved, {rejected} rejected", "info")

            elif node == "execution":
                filled = len(state_data.get("executed_orders", []))
                failed = len(state_data.get("failed_orders", []))
                yield _line(f"       Orders: {filled} filled, {failed} failed", "success" if failed == 0 else "warn")
                for order in state_data.get("executed_orders", []):
                    sym = order.get("symbol", "") if isinstance(order, dict) else getattr(order, "symbol", "")
                    side = order.get("side", "") if isinstance(order, dict) else getattr(order, "side", "")
                    price = order.get("price", 0) if isinstance(order, dict) else getattr(order, "price", 0)
                    size = order.get("size", 0) if isinstance(order, dict) else getattr(order, "size", 0)
                    side_val = side.value if hasattr(side, "value") else str(side)
                    style = "success" if side_val == "buy" else "error"
                    yield _line(
                        f"       → {side_val.upper():5s} {sym} {size:.4f} @ ${price:,.2f}",
                        style,
                    )

            elif node == "portfolio_manager":
                port = state_data.get("portfolio")
                if port:
                    eq = port.get("total_equity", 0) if isinstance(port, dict) else getattr(port, "total_equity", 0)
                    dd = port.get("current_drawdown", 0) if isinstance(port, dict) else getattr(port, "current_drawdown", 0)
                    yield _line(f"       Equity: ${eq:,.2f}  Drawdown: {dd:.2%}", "info")

            elif node == "learning":
                msgs = state_data.get("agent_messages", [])
                learning_msg = next((m for m in reversed(msgs) if "[Learning]" in m), None)
                if learning_msg:
                    yield _line(f"       {learning_msg[learning_msg.find(']')+2:].strip()[:70]}", "muted")

            # Store last state
            if node == "learning":
                final_state = TradingState(**state_data) if isinstance(state_data, dict) else state_data

    except Exception as exc:
        yield _line(f"  ✗ Cycle error: {exc}", "error")
        logger.error(f"[Terminal] cycle error: {exc}", exc_info=True)
        return

    total = asyncio.get_event_loop().time() - t0
    yield _line("", "normal")
    yield _line(f"  Cycle complete in {total:.1f}s", "success")

    if final_state:
        errors = final_state.errors
        if errors:
            yield _line(f"  Warnings: {len(errors)}", "warn")
            for e in errors[:3]:
                yield _line(f"    · {e[:70]}", "dim")
    yield _line("", "normal")


# ── portfolio ─────────────────────────────────────────────────────────────────

async def cmd_portfolio(_args: List[str]) -> AsyncIterator[Line]:
    from services.database import DatabaseService

    db = DatabaseService()
    snap = await db.get_portfolio_snapshot()

    yield _line("", "normal")
    yield _line("  ─── Portfolio ────────────────────────────────", "muted")

    if not snap:
        yield _line("  No portfolio data yet. Run a cycle first.", "warn")
        yield _line("", "normal")
        return

    dd_style = "error" if snap.current_drawdown > 0.10 else "warn" if snap.current_drawdown > 0.05 else "success"
    pnl_style = "success" if snap.realized_pnl >= 0 else "error"

    yield _line(f"  Total Equity     ${snap.total_equity:>12,.2f}", "gold")
    yield _line(f"  Cash             ${snap.cash:>12,.2f}", "normal")
    yield _line(f"  Positions Value  ${snap.positions_value:>12,.2f}", "normal")
    yield _line(f"  Realized PnL     ${snap.realized_pnl:>+12,.2f}", pnl_style)
    yield _line(f"  Unrealized PnL   ${snap.unrealized_pnl:>+12,.2f}", "info")
    yield _line(f"  Peak Equity      ${snap.peak_equity:>12,.2f}", "muted")
    yield _line(f"  Drawdown         {snap.current_drawdown:>12.2%}", dd_style)
    yield _line("", "normal")

    if snap.open_positions:
        yield _line("  Open Positions:", "gold")
        for sym, pos in snap.open_positions.items():
            val = pos.get("value", 0) if isinstance(pos, dict) else 0
            yield _line(f"    {sym:<16} ${val:,.2f}", "info")
        yield _line("", "normal")


# ── signals ───────────────────────────────────────────────────────────────────

async def cmd_signals(_args: List[str]) -> AsyncIterator[Line]:
    from api.routes.signals import _last_cycle_state

    yield _line("", "normal")

    if _last_cycle_state is None:
        yield _line("  No cycle run yet. Use  cycle  to start one.", "warn")
        yield _line("", "normal")
        return

    state = _last_cycle_state
    yield _line(f"  ─── Signals — Cycle {state.cycle_id[:8]} ─────────────", "muted")
    yield _line(f"  Regime: {state.market_regime.value}", "info")
    yield _line(f"  Raw: {len(state.raw_signals)}   Filtered: {len(state.filtered_signals)}", "muted")
    yield _line("", "normal")

    if not state.filtered_signals:
        yield _line("  No signals passed the filter this cycle.", "dim")
        yield _line("", "normal")
        return

    yield _line("  " + "─" * 72, "muted")
    for s in state.filtered_signals:
        direction_style = "success" if s.direction.value == "long" else "error"
        rr = abs(s.take_profit - s.entry_price) / abs(s.entry_price - s.stop_loss) if abs(s.entry_price - s.stop_loss) > 0 else 0
        yield _line(
            f"  {s.symbol:<12} {s.direction.value.upper():<6}  "
            f"Entry ${s.entry_price:>10,.4f}  "
            f"SL ${s.stop_loss:>10,.4f}  "
            f"TP ${s.take_profit:>10,.4f}",
            direction_style,
        )
        yield _line(
            f"  {'':12} {s.strategy:<20}  "
            f"Conf {s.confidence:.0%}  "
            f"R:R {rr:.1f}x  "
            f"{s.strength.value}",
            "muted",
        )
        if s.reasoning:
            yield _line(f"  {'':12} {s.reasoning[:65]}", "dim")
        yield _line("", "normal")


# ── trades ────────────────────────────────────────────────────────────────────

async def cmd_trades(args: List[str]) -> AsyncIterator[Line]:
    from services.database import DatabaseService

    limit = 20
    if args:
        try:
            limit = min(500, max(1, int(args[0])))
        except ValueError:
            pass

    db = DatabaseService()
    trades = await db.get_recent_trades(limit=limit)

    yield _line("", "normal")
    yield _line(f"  ─── Recent Trades (last {limit}) ─────────────────", "muted")
    yield _line("", "normal")

    if not trades:
        yield _line("  No trades recorded yet.", "dim")
        yield _line("", "normal")
        return

    header = f"  {'#':<4}  {'Symbol':<12}  {'Side':<5}  {'Price':>12}  {'Size':>12}  {'PnL':>10}  {'Strategy':<20}  Time"
    yield _line(header, "gold")
    yield _line("  " + "─" * 96, "muted")

    for i, t in enumerate(trades, 1):
        pnl = t.get("pnl", 0) or 0
        side = (t.get("side") or "").upper()
        pnl_str = f"{pnl:+.2f}" if pnl else "   –"
        pnl_style = "success" if pnl > 0 else "error" if pnl < 0 else "muted"
        ts = str(t.get("created_at", ""))[:16]
        side_style = "success" if side == "BUY" else "error"

        line = (
            f"  {i:<4}  {t.get('symbol',''):<12}  "
            f"{side:<5}  "
            f"${t.get('price', 0):>11,.4f}  "
            f"{t.get('size', 0):>12.6f}  "
            f"{pnl_str:>10}  "
            f"{str(t.get('strategy','')):<20}  "
            f"{ts}"
        )
        yield _line(line, "normal")

    yield _line("", "normal")


# ── weights ───────────────────────────────────────────────────────────────────

async def cmd_weights(args: List[str]) -> AsyncIterator[Line]:
    from services.database import DatabaseService

    db = DatabaseService()
    yield _line("", "normal")
    yield _line("  ─── Strategy Weights ────────────────────────", "muted")
    yield _line("", "normal")

    # Update weight if args provided: weights trend_following 0.35
    if len(args) >= 2:
        strategy = args[0].lower().replace("-", "_")
        try:
            new_val = float(args[1])
            if not 0.0 < new_val <= 1.0:
                yield _line("  Error: weight must be between 0 and 1", "error")
                return

            # Read current, update, normalize
            current = {
                "trend_following":    settings.weight_trend_following,
                "momentum_breakout":  settings.weight_momentum_breakout,
                "mean_reversion":     settings.weight_mean_reversion,
                "volatility_arb":     settings.weight_volatility_arb,
                "portfolio_rotation": settings.weight_portfolio_rotation,
            }
            if strategy not in current:
                yield _line(f"  Unknown strategy: {strategy}", "error")
                yield _line(f"  Valid: {', '.join(current.keys())}", "muted")
                return

            current[strategy] = new_val
            total = sum(current.values())
            normalized = {k: v / total for k, v in current.items()}
            await db.save_strategy_weights(normalized)
            yield _line(f"  Updated {strategy} → {new_val:.3f} (normalized)", "success")
            yield _line("", "normal")

            for name, w in normalized.items():
                bar = "█" * int(w * 30)
                yield _line(f"  {name:<22} {bar:<30} {w:.1%}", "info")
            yield _line("", "normal")
            return
        except ValueError:
            yield _line(f"  Invalid value: {args[1]}", "error")
            return

    # Display current weights
    weights = {
        "trend_following":    settings.weight_trend_following,
        "momentum_breakout":  settings.weight_momentum_breakout,
        "mean_reversion":     settings.weight_mean_reversion,
        "volatility_arb":     settings.weight_volatility_arb,
        "portfolio_rotation": settings.weight_portfolio_rotation,
    }

    from api.routes.signals import _last_cycle_state
    if _last_cycle_state and _last_cycle_state.strategy_weights:
        weights = _last_cycle_state.strategy_weights

    for name, w in weights.items():
        bar = "█" * int(w * 30)
        yield _line(f"  {name:<22} {bar:<30} {w:.1%}", "info")
    yield _line("", "normal")
    yield _line("  Usage: weights <strategy> <value>", "dim")
    yield _line("  e.g.   weights trend_following 0.40", "dim")
    yield _line("", "normal")


# ── regime ────────────────────────────────────────────────────────────────────

async def cmd_regime(_args: List[str]) -> AsyncIterator[Line]:
    from services.database import DatabaseService
    from api.routes.signals import _last_cycle_state

    yield _line("", "normal")
    yield _line("  ─── Market Regime ───────────────────────────", "muted")
    yield _line("", "normal")

    if _last_cycle_state:
        regime = _last_cycle_state.market_regime.value
        yield _line(f"  Current    {regime.replace('_',' ').upper()}", "gold")
        yield _line("", "normal")

    db = DatabaseService()
    history = await db.get_regime_history(limit=15)
    if history:
        yield _line("  Recent History:", "info")
        for r in history:
            ts = str(r.get("recorded_at", ""))[:16]
            regime_val = r.get("regime", "")
            conf = r.get("confidence", 0) or 0
            yield _line(
                f"  {ts}  {regime_val:<20}  conf {conf:.0%}",
                "muted",
            )
    yield _line("", "normal")


# ── scheduler ────────────────────────────────────────────────────────────────

async def cmd_scheduler(args: List[str]) -> AsyncIterator[Line]:
    from core.scheduler import get_scheduler

    sch = get_scheduler()
    yield _line("", "normal")

    if not args:
        st = sch.status()
        yield _line("  ─── Scheduler ───────────────────────────────", "muted")
        yield _line(f"  Status     {'RUNNING' if st['running'] else 'STOPPED'}", "success" if st["running"] else "warn")
        yield _line(f"  Interval   {st['interval_secs']}s", "normal")
        yield _line(f"  Cycles     {st['cycle_count']}", "info")
        if st["last_run"]:
            yield _line(f"  Last run   {st['last_run'][:19]}Z", "muted")
        if st["secs_until_next"] is not None:
            m, s = divmod(st["secs_until_next"], 60)
            yield _line(f"  Next run   in {m}m {s}s", "info")
        yield _line("", "normal")
        yield _line("  Usage: scheduler start | stop | interval <secs>", "dim")
        yield _line("", "normal")
        return

    sub = args[0].lower()
    if sub == "start":
        result = sch.start()
        yield _line(f"  Scheduler {result}", "success" if result == "started" else "warn")
    elif sub == "stop":
        result = sch.stop()
        yield _line(f"  Scheduler {result}", "success" if result == "stopped" else "warn")
    elif sub == "restart":
        sch.stop()
        result = sch.start()
        yield _line(f"  Scheduler restarted", "success")
    elif sub == "interval" and len(args) > 1:
        try:
            secs = int(args[1])
            sch.set_interval(secs)
            yield _line(f"  Interval set to {secs}s", "success")
        except ValueError:
            yield _line(f"  Invalid interval: {args[1]}", "error")
    else:
        yield _line(f"  Unknown sub-command: {sub}", "error")
        yield _line("  Usage: scheduler start | stop | interval <secs>", "dim")

    yield _line("", "normal")


# ── kill switch ───────────────────────────────────────────────────────────────

async def cmd_kill(_args: List[str]) -> AsyncIterator[Line]:
    from risk.kill_switch import KillSwitch

    ks = KillSwitch(redis_url=settings.redis_url)
    await ks._redis.set("sfomo:kill_switch:triggered", "1")
    await ks.close()

    yield _line("", "normal")
    yield _line("  ⚠  KILL SWITCH TRIGGERED", "error")
    yield _line("  All trading halted. Use  reset-kill  to re-enable.", "warn")
    yield _line("", "normal")


async def cmd_reset_kill(_args: List[str]) -> AsyncIterator[Line]:
    from risk.kill_switch import KillSwitch

    ks = KillSwitch(redis_url=settings.redis_url)
    await ks.reset()
    await ks.close()

    yield _line("", "normal")
    yield _line("  Kill switch reset. Trading re-enabled.", "success")
    yield _line("", "normal")


# ── backtest ──────────────────────────────────────────────────────────────────

async def cmd_backtest(args: List[str]) -> AsyncIterator[Line]:
    symbol = args[0].upper() if args else "BTC/USDT"
    if "/" not in symbol:
        symbol = f"{symbol}/USDT"
    days = 30
    if len(args) > 1:
        try:
            days = max(7, min(365, int(args[1])))
        except ValueError:
            pass

    yield _line("", "normal")
    yield _line(f"  ─── Backtest: {symbol} ({days}d) ───────────────────", "muted")
    yield _line("  Fetching historical data…", "info")

    from services.exchange import ExchangeService
    from strategies.trend_following import TrendFollowingStrategy
    from strategies.momentum_breakout import MomentumBreakoutStrategy
    from strategies.mean_reversion import MeanReversionStrategy

    exchange = ExchangeService()
    try:
        candles = await exchange.fetch_ohlcv(symbol, "1h", limit=days * 24)
    except Exception as exc:
        yield _line(f"  Failed to fetch data: {exc}", "error")
        await exchange.close()
        return
    finally:
        await exchange.close()

    if not candles or len(candles.get("close", [])) < 50:
        yield _line("  Insufficient candle data returned.", "warn")
        yield _line("", "normal")
        return

    closes = candles["close"]
    price_now = closes[-1]
    price_start = closes[0]
    bah_return = (price_now - price_start) / price_start

    yield _line(f"  Candles loaded: {len(closes)}", "muted")
    yield _line(f"  Price range:    ${min(closes):,.2f} → ${max(closes):,.2f}", "muted")
    yield _line(f"  B&H Return:     {bah_return:+.2%}", "info")
    yield _line("", "normal")

    strategies = [
        ("Trend Following",   TrendFollowingStrategy()),
        ("Momentum Breakout", MomentumBreakoutStrategy()),
        ("Mean Reversion",    MeanReversionStrategy()),
    ]

    yield _line("  Strategy Signal Summary:", "gold")
    yield _line(f"  {'Strategy':<22}  {'Signals':>8}  {'Long':>6}  {'Short':>6}  {'Avg Conf':>9}", "muted")
    yield _line("  " + "─" * 60, "muted")

    for name, strat in strategies:
        try:
            signals = await strat.generate_signals(
                candles={symbol: candles},
                order_books={},
                market_structure={},
                funding_rates={},
            )
            longs  = sum(1 for s in signals if s.direction.value == "long")
            shorts = sum(1 for s in signals if s.direction.value == "short")
            avg_conf = sum(s.confidence for s in signals) / len(signals) if signals else 0
            yield _line(
                f"  {name:<22}  {len(signals):>8}  {longs:>6}  {shorts:>6}  {avg_conf:>8.0%}",
                "normal",
            )
        except Exception as exc:
            yield _line(f"  {name:<22}  error: {exc}", "error")

    yield _line("", "normal")
    yield _line("  Note: full vectorbt backtest via  make backtest  in the shell.", "dim")
    yield _line("", "normal")


# ── agents ────────────────────────────────────────────────────────────────────

async def cmd_agents(_args: List[str]) -> AsyncIterator[Line]:
    from api.routes.signals import _last_cycle_state

    yield _line("", "normal")
    yield _line("  ─── Agent Pipeline Log ──────────────────────", "muted")
    yield _line("", "normal")

    if _last_cycle_state is None:
        yield _line("  No cycle run yet.", "dim")
        yield _line("", "normal")
        return

    for msg in _last_cycle_state.agent_messages:
        style = "error" if "KILL" in msg or "ERROR" in msg else "info" if "[Execution]" in msg else "muted"
        yield _line(f"  {msg}", style)
    yield _line("", "normal")


# ── logs ──────────────────────────────────────────────────────────────────────

async def cmd_logs(args: List[str]) -> AsyncIterator[Line]:
    from api.routes.signals import _last_cycle_state

    limit = 50
    if args:
        try:
            limit = min(200, max(1, int(args[0])))
        except ValueError:
            pass

    yield _line("", "normal")
    yield _line(f"  ─── Agent Messages (last {limit}) ────────────────", "muted")
    yield _line("", "normal")

    if _last_cycle_state is None:
        yield _line("  No messages yet.", "dim")
        yield _line("", "normal")
        return

    messages = _last_cycle_state.agent_messages[-limit:]
    for msg in messages:
        style = "error" if any(x in msg for x in ["KILL", "ERROR", "CRITICAL"]) else "normal"
        yield _line(f"  {msg[:100]}", style)
    yield _line("", "normal")


# ── balances ──────────────────────────────────────────────────────────────────

async def cmd_balances(_args: List[str]) -> AsyncIterator[Line]:
    from services.exchange import ExchangeService

    yield _line("", "normal")
    yield _line("  ─── Exchange Balances ───────────────────────", "muted")
    yield _line("", "normal")

    exchange = ExchangeService()
    try:
        raw = await exchange.fetch_balance()
    except Exception as exc:
        yield _line(f"  Exchange error: {exc}", "error")
        yield _line("", "normal")
        await exchange.close()
        return
    finally:
        await exchange.close()

    total_map = raw.get("total", {})
    free_map = raw.get("free", {})
    used_map = raw.get("used", {})

    coins = []
    for currency, total in total_map.items():
        if currency in ("info", "timestamp", "datetime"):
            continue
        if not isinstance(total, (int, float)) or total <= 0:
            continue
        coins.append((currency, float(free_map.get(currency) or 0), float(used_map.get(currency) or 0), float(total)))

    if not coins:
        yield _line("  No balances found.", "dim")
        yield _line("", "normal")
        return

    coins.sort(key=lambda x: x[3], reverse=True)
    yield _line(f"  {'Currency':<10}  {'Free':>18}  {'Locked':>18}  {'Total':>18}", "gold")
    yield _line("  " + "─" * 70, "muted")
    for currency, free, locked, total in coins:
        yield _line(
            f"  {currency:<10}  {free:>18,.8f}  {locked:>18,.8f}  {total:>18,.8f}",
            "info",
        )
    yield _line("", "normal")


# ── deposit ───────────────────────────────────────────────────────────────────

async def cmd_deposit(args: List[str]) -> AsyncIterator[Line]:
    from services.exchange import ExchangeService

    if not args:
        yield _line("  Usage: deposit <CURRENCY> [NETWORK]", "error")
        yield _line("  e.g.   deposit USDT TRC20", "dim")
        yield _line("", "normal")
        return

    currency = args[0].upper()
    network = args[1] if len(args) > 1 else None

    yield _line("", "normal")
    yield _line(f"  Fetching {currency} deposit address{f' ({network})' if network else ''}…", "info")

    exchange = ExchangeService()
    try:
        result = await exchange.fetch_deposit_address(currency, network)
    except Exception as exc:
        yield _line(f"  Exchange error: {exc}", "error")
        yield _line("", "normal")
        await exchange.close()
        return
    finally:
        await exchange.close()

    address = result.get("address", "")
    tag = result.get("tag")
    net = result.get("network") or network or ""

    yield _line("", "normal")
    yield _line(f"  ─── {currency} Deposit Address ─────────────────", "muted")
    yield _line(f"  Network   {net}", "info")
    yield _line(f"  Address   {address}", "gold")
    if tag:
        yield _line(f"  Memo/Tag  {tag}", "warn")
        yield _line("  ⚠ Memo/Tag is required for this currency", "warn")
    yield _line("", "normal")
    yield _line(f"  ⚠ Only send {currency} on {net or 'this'} network", "dim")
    yield _line("", "normal")


# ── withdraw ──────────────────────────────────────────────────────────────────

async def cmd_withdraw(args: List[str]) -> AsyncIterator[Line]:
    from services.exchange import ExchangeService
    from services.database import DatabaseService

    # Parse: withdraw <CURRENCY> <AMOUNT> <ADDRESS> [NETWORK] [--confirm]
    confirm = "--confirm" in args
    clean_args = [a for a in args if a != "--confirm"]

    if len(clean_args) < 3:
        yield _line("", "normal")
        yield _line("  Usage: withdraw <CURRENCY> <AMOUNT> <ADDRESS> [NETWORK] [--confirm]", "error")
        yield _line("  e.g.   withdraw USDT 100 TXyz... TRC20 --confirm", "dim")
        yield _line("", "normal")
        yield _line("  Omit --confirm to preview without executing.", "muted")
        yield _line("", "normal")
        return

    currency = clean_args[0].upper()
    try:
        amount = float(clean_args[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        yield _line(f"  Invalid amount: {clean_args[1]}", "error")
        yield _line("", "normal")
        return

    address = clean_args[2]
    network = clean_args[3] if len(clean_args) > 3 else None

    yield _line("", "normal")
    yield _line("  ─── Withdrawal Preview ──────────────────────", "muted")
    yield _line(f"  Currency  {currency}", "info")
    yield _line(f"  Amount    {amount:,.8f}", "warn")
    yield _line(f"  Address   {address[:20]}…{address[-8:] if len(address) > 28 else ''}", "gold")
    if network:
        yield _line(f"  Network   {network}", "info")
    yield _line("", "normal")

    if not confirm:
        yield _line("  DRY RUN — not submitted.", "muted")
        yield _line("  Add --confirm to execute: withdraw ... --confirm", "dim")
        yield _line("", "normal")
        return

    yield _line("  Submitting withdrawal…", "warn")
    exchange = ExchangeService()
    db = DatabaseService()
    try:
        result = await exchange.withdraw(
            currency=currency,
            amount=amount,
            address=address,
            network=network,
        )
        wid = str(result.get("id", ""))
        await db.record_audit_log(
            action="withdrawal",
            symbol=currency,
            side="out",
            size=amount,
            order_id=wid,
            status="submitted",
            detail=f"addr={address[:20]} net={network}",
            cycle_id="",
        )
        yield _line(f"  ✓ Submitted — ID: {wid or 'pending'}", "success")
    except Exception as exc:
        yield _line(f"  ✗ Failed: {exc}", "error")
        await db.record_audit_log(
            action="withdrawal_failed",
            symbol=currency,
            side="out",
            size=amount,
            status="failed",
            detail=str(exc)[:200],
            cycle_id="",
        )
    finally:
        await exchange.close()

    yield _line("", "normal")


# ── deposits history ──────────────────────────────────────────────────────────

async def cmd_deposits(args: List[str]) -> AsyncIterator[Line]:
    from services.exchange import ExchangeService

    currency: Optional[str] = None
    limit = 20
    for arg in args:
        if arg.isdigit():
            limit = min(100, max(1, int(arg)))
        elif arg.isalpha():
            currency = arg.upper()

    yield _line("", "normal")
    yield _line(f"  ─── Deposit History{f' ({currency})' if currency else ''} ──────────────────", "muted")
    yield _line("", "normal")

    exchange = ExchangeService()
    try:
        txs = await exchange.fetch_deposits(currency, limit)
    except Exception as exc:
        yield _line(f"  Exchange error: {exc}", "error")
        yield _line("", "normal")
        await exchange.close()
        return
    finally:
        await exchange.close()

    if not txs:
        yield _line("  No deposits found.", "dim")
        yield _line("", "normal")
        return

    yield _line(f"  {'Time':<20}  {'Currency':<8}  {'Amount':>14}  {'Status':<12}  TxID", "gold")
    yield _line("  " + "─" * 80, "muted")
    for tx in txs:
        ts = str(tx.get("datetime") or tx.get("timestamp") or "")[:16]
        amt = float(tx.get("amount") or 0)
        txid = str(tx.get("txid") or "")[:14]
        status = str(tx.get("status") or "")
        ccy = str(tx.get("currency") or "")
        yield _line(
            f"  {ts:<20}  {ccy:<8}  {amt:>14,.8f}  {status:<12}  {txid}",
            "success" if status == "ok" else "muted",
        )
    yield _line("", "normal")


# ── withdrawals history ───────────────────────────────────────────────────────

async def cmd_withdrawals(args: List[str]) -> AsyncIterator[Line]:
    from services.exchange import ExchangeService

    currency: Optional[str] = None
    limit = 20
    for arg in args:
        if arg.isdigit():
            limit = min(100, max(1, int(arg)))
        elif arg.isalpha():
            currency = arg.upper()

    yield _line("", "normal")
    yield _line(f"  ─── Withdrawal History{f' ({currency})' if currency else ''} ─────────────────", "muted")
    yield _line("", "normal")

    exchange = ExchangeService()
    try:
        txs = await exchange.fetch_withdrawals(currency, limit)
    except Exception as exc:
        yield _line(f"  Exchange error: {exc}", "error")
        yield _line("", "normal")
        await exchange.close()
        return
    finally:
        await exchange.close()

    if not txs:
        yield _line("  No withdrawals found.", "dim")
        yield _line("", "normal")
        return

    yield _line(f"  {'Time':<20}  {'Currency':<8}  {'Amount':>14}  {'Status':<12}  Address", "gold")
    yield _line("  " + "─" * 80, "muted")
    for tx in txs:
        ts = str(tx.get("datetime") or tx.get("timestamp") or "")[:16]
        amt = float(tx.get("amount") or 0)
        addr = str(tx.get("address") or "")
        addr_short = f"{addr[:10]}…{addr[-6:]}" if len(addr) > 16 else addr
        status = str(tx.get("status") or "")
        ccy = str(tx.get("currency") or "")
        yield _line(
            f"  {ts:<20}  {ccy:<8}  {amt:>14,.8f}  {status:<12}  {addr_short}",
            "error" if status in ("failed", "canceled") else "muted",
        )
    yield _line("", "normal")


# ── misc ──────────────────────────────────────────────────────────────────────

async def cmd_ping(_args: List[str]) -> AsyncIterator[Line]:
    import time
    from services.database import AsyncSessionLocal
    from sqlalchemy import text

    yield _line("", "normal")

    t0 = time.perf_counter()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ms = (time.perf_counter() - t0) * 1000
        yield _line(f"  Database   {db_ms:.1f}ms", "success")
    except Exception as exc:
        yield _line(f"  Database   ERROR: {exc}", "error")

    yield _line(f"  Exchange   {settings.exchange_id} ({'sandbox' if settings.exchange_sandbox else 'live'})", "info")
    yield _line("", "normal")


async def cmd_version(_args: List[str]) -> AsyncIterator[Line]:
    import sys
    yield _line("", "normal")
    yield _line("  SFOMO  v1.0.0", "gold")
    yield _line(f"  Python  {sys.version.split()[0]}", "muted")
    yield _line(f"  Env     {settings.app_env}", "muted")
    yield _line(f"  Model   {settings.openai_model}", "muted")
    yield _line("", "normal")


async def cmd_clear(_args: List[str]) -> AsyncIterator[Line]:
    yield ("__CLEAR__", "clear")


async def cmd_unknown(name: str) -> AsyncIterator[Line]:
    yield _line("", "normal")
    yield _line(f"  Unknown command: {name}", "error")
    yield _line("  Type  help  to see available commands.", "dim")
    yield _line("", "normal")


# ── Dispatch table ────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Callable] = {
    "help":        cmd_help,
    "status":      cmd_status,
    "cycle":       cmd_cycle,
    "portfolio":   cmd_portfolio,
    "signals":     cmd_signals,
    "trades":      cmd_trades,
    "weights":     cmd_weights,
    "regime":      cmd_regime,
    "scheduler":   cmd_scheduler,
    "kill":        cmd_kill,
    "reset-kill":  cmd_reset_kill,
    "backtest":    cmd_backtest,
    "agents":      cmd_agents,
    "logs":        cmd_logs,
    "balances":    cmd_balances,
    "deposit":     cmd_deposit,
    "withdraw":    cmd_withdraw,
    "deposits":    cmd_deposits,
    "withdrawals": cmd_withdrawals,
    "ping":        cmd_ping,
    "version":     cmd_version,
    "clear":       cmd_clear,
}


async def dispatch(raw: str) -> AsyncIterator[Line]:
    """Parse raw input and dispatch to the correct handler."""
    raw = raw.strip()
    if not raw:
        return

    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()

    if not parts:
        return

    name = parts[0].lower()
    args = parts[1:]

    handler = _REGISTRY.get(name)
    if handler is None:
        async for line in cmd_unknown(name):
            yield line
        return

    try:
        async for line in handler(args):
            yield line
    except Exception as exc:
        logger.error(f"[Commands] {name} error: {exc}", exc_info=True)
        yield _line(f"  Command error: {exc}", "error")
        yield _line("", "normal")
