"""Simple vectorbt-style backtest harness for SFOMO strategies."""
from __future__ import annotations

import asyncio
import sys

import pandas as pd

sys.path.insert(0, "/app")

from strategies.trend_following import TrendFollowingStrategy
from strategies.momentum_breakout import MomentumBreakoutStrategy
from strategies.mean_reversion import MeanReversionStrategy


async def run_backtest(symbol: str = "BTC/USDT", days: int = 90):
    import ccxt.async_support as ccxt

    exchange = ccxt.binance({"enableRateLimit": True})
    exchange.set_sandbox_mode(True)

    print(f"Fetching {days*24} candles for {symbol}...")
    raw = await exchange.fetch_ohlcv(symbol, "1h", limit=days * 24)
    await exchange.close()

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)

    candles = {
        symbol: {
            "timestamp": df.index.astype(int).tolist(),
            "open": df["open"].tolist(),
            "high": df["high"].tolist(),
            "low": df["low"].tolist(),
            "close": df["close"].tolist(),
            "volume": df["volume"].tolist(),
        }
    }

    strategies = [
        TrendFollowingStrategy(),
        MomentumBreakoutStrategy(),
        MeanReversionStrategy(),
    ]

    for strat in strategies:
        signals = await strat.generate_signals(
            candles=candles,
            order_books={},
            market_structure={},
            funding_rates={},
        )
        print(f"\n{strat.name}: {len(signals)} signals")
        for s in signals[:5]:
            rr = abs(s.take_profit - s.entry_price) / abs(s.entry_price - s.stop_loss)
            print(
                f"  {s.direction.value:5s} @ {s.entry_price:.2f} | "
                f"SL={s.stop_loss:.2f} TP={s.take_profit:.2f} | "
                f"R:R={rr:.1f} conf={s.confidence:.2f}"
            )


if __name__ == "__main__":
    asyncio.run(run_backtest())
