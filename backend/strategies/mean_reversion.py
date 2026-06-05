"""Mean Reversion — Bollinger Bands + RSI divergence."""
from __future__ import annotations

import math
from typing import Any, Dict, List

from core.state import SignalDirection, SignalStrength, TradingSignal
from strategies.base import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    """Buy oversold / sell overbought conditions using Bollinger Bands."""

    BB_PERIOD = 20
    BB_STD = 2.0
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70

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

            if len(closes) < self.BB_PERIOD + 2:
                continue

            price = closes[-1]
            sma = self._compute_sma(closes, self.BB_PERIOD)
            std = math.sqrt(
                sum((c - sma) ** 2 for c in closes[-self.BB_PERIOD:]) / self.BB_PERIOD
            )
            upper_band = sma + self.BB_STD * std
            lower_band = sma - self.BB_STD * std
            rsi = self._compute_rsi(closes)
            atr = self._compute_atr(highs, lows, closes)

            if not atr or std == 0:
                continue

            bb_position = (price - lower_band) / (upper_band - lower_band) if (upper_band - lower_band) > 0 else 0.5

            # Oversold — long signal
            if price <= lower_band and rsi <= self.RSI_OVERSOLD:
                deviation = (lower_band - price) / std
                confidence = min(0.85, 0.55 + deviation * 0.1)
                signals.append(
                    TradingSignal(
                        symbol=symbol,
                        strategy="mean_reversion",
                        direction=SignalDirection.LONG,
                        strength=SignalStrength.STRONG if confidence > 0.72 else SignalStrength.MODERATE,
                        entry_price=price,
                        stop_loss=price - atr * 1.5,
                        take_profit=sma,
                        confidence=confidence,
                        reasoning=(
                            f"Price at lower BB ({price:.4f} <= {lower_band:.4f}), "
                            f"RSI={rsi:.1f}"
                        ),
                    )
                )

            # Overbought — short signal
            elif price >= upper_band and rsi >= self.RSI_OVERBOUGHT:
                deviation = (price - upper_band) / std
                confidence = min(0.85, 0.55 + deviation * 0.1)
                signals.append(
                    TradingSignal(
                        symbol=symbol,
                        strategy="mean_reversion",
                        direction=SignalDirection.SHORT,
                        strength=SignalStrength.STRONG if confidence > 0.72 else SignalStrength.MODERATE,
                        entry_price=price,
                        stop_loss=price + atr * 1.5,
                        take_profit=sma,
                        confidence=confidence,
                        reasoning=(
                            f"Price at upper BB ({price:.4f} >= {upper_band:.4f}), "
                            f"RSI={rsi:.1f}"
                        ),
                    )
                )

        return signals
