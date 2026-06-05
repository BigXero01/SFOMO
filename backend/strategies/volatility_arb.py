"""Volatility Arbitrage — realized vs implied vol spread + funding rate signals."""
from __future__ import annotations

import math
from typing import Any, Dict, List

from core.state import SignalDirection, SignalStrength, TradingSignal
from strategies.base import BaseStrategy


class VolatilityArbStrategy(BaseStrategy):
    """Exploit funding rate extremes and volatility regime transitions."""

    FUNDING_EXTREME = 0.001   # 0.1% per 8h — extremely elevated
    FUNDING_LOW = -0.0005
    VOL_LOOKBACK = 20

    async def generate_signals(
        self,
        candles: Dict[str, Any],
        order_books: Dict[str, Any],
        market_structure: Dict[str, Any],
        funding_rates: Dict[str, float],
    ) -> List[TradingSignal]:
        signals = []

        for symbol, data in candles.items():
            closes = data.get("close", [])
            highs = data.get("high", [])
            lows = data.get("low", [])

            if len(closes) < self.VOL_LOOKBACK + 2:
                continue

            price = closes[-1]
            atr = self._compute_atr(highs, lows, closes)
            rsi = self._compute_rsi(closes)
            funding = funding_rates.get(symbol, 0.0)

            if not price or not atr:
                continue

            # Realized vol (annualized)
            log_returns = [
                math.log(closes[i] / closes[i - 1])
                for i in range(1, len(closes))
                if closes[i - 1] > 0
            ]
            if len(log_returns) < self.VOL_LOOKBACK:
                continue
            rv = math.sqrt(
                sum(r ** 2 for r in log_returns[-self.VOL_LOOKBACK:]) / self.VOL_LOOKBACK
            ) * math.sqrt(365 * 24)  # hourly to annualized

            # High positive funding → longs are crowded → short bias
            if funding >= self.FUNDING_EXTREME and rsi > 60:
                confidence = min(0.82, 0.60 + (funding / self.FUNDING_EXTREME) * 0.05)
                signals.append(
                    TradingSignal(
                        symbol=symbol,
                        strategy="volatility_arb",
                        direction=SignalDirection.SHORT,
                        strength=SignalStrength.MODERATE,
                        entry_price=price,
                        stop_loss=price + atr * 2,
                        take_profit=price - atr * 3,
                        confidence=confidence,
                        reasoning=f"Extreme positive funding={funding:.4%}, crowd long → fade",
                        metadata={"funding_rate": funding, "realized_vol": rv},
                    )
                )

            # Negative funding → shorts crowded → long bias
            elif funding <= self.FUNDING_LOW and rsi < 40:
                confidence = min(0.82, 0.60 + abs(funding / self.FUNDING_LOW) * 0.05)
                signals.append(
                    TradingSignal(
                        symbol=symbol,
                        strategy="volatility_arb",
                        direction=SignalDirection.LONG,
                        strength=SignalStrength.MODERATE,
                        entry_price=price,
                        stop_loss=price - atr * 2,
                        take_profit=price + atr * 3,
                        confidence=confidence,
                        reasoning=f"Negative funding={funding:.4%}, crowd short → fade",
                        metadata={"funding_rate": funding, "realized_vol": rv},
                    )
                )

        return signals
