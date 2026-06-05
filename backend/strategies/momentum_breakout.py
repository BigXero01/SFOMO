"""Momentum Breakout — Donchian channel + volume confirmation."""
from __future__ import annotations

from typing import Any, Dict, List

from core.state import SignalDirection, SignalStrength, TradingSignal
from strategies.base import BaseStrategy


class MomentumBreakoutStrategy(BaseStrategy):
    """Price breakout above N-period high with volume surge."""

    LOOKBACK = 20
    VOLUME_MULTIPLIER = 1.5

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
            volumes = data.get("volume", [])

            if len(closes) < self.LOOKBACK + 2:
                continue

            price = closes[-1]
            atr = self._compute_atr(highs, lows, closes)
            rsi = self._compute_rsi(closes)

            period_high = max(highs[-self.LOOKBACK - 1 : -1])
            period_low = min(lows[-self.LOOKBACK - 1 : -1])
            avg_volume = sum(volumes[-self.LOOKBACK:]) / self.LOOKBACK if volumes else 0
            last_volume = volumes[-1] if volumes else 0
            volume_surge = last_volume >= avg_volume * self.VOLUME_MULTIPLIER

            if not atr or not price:
                continue

            # Bullish breakout
            if price > period_high and volume_surge and rsi < 80:
                breakout_strength = (price - period_high) / atr
                confidence = min(0.90, 0.60 + breakout_strength * 0.05)
                signals.append(
                    TradingSignal(
                        symbol=symbol,
                        strategy="momentum_breakout",
                        direction=SignalDirection.LONG,
                        strength=SignalStrength.STRONG if confidence > 0.75 else SignalStrength.MODERATE,
                        entry_price=price,
                        stop_loss=period_high - atr * 0.5,
                        take_profit=price + atr * 3,
                        confidence=confidence,
                        reasoning=(
                            f"Breakout above {self.LOOKBACK}-period high={period_high:.4f} "
                            f"volume={last_volume:.0f} ({volume_surge=})"
                        ),
                    )
                )

            # Bearish breakdown
            elif price < period_low and volume_surge and rsi > 20:
                breakdown_strength = (period_low - price) / atr
                confidence = min(0.90, 0.60 + breakdown_strength * 0.05)
                signals.append(
                    TradingSignal(
                        symbol=symbol,
                        strategy="momentum_breakout",
                        direction=SignalDirection.SHORT,
                        strength=SignalStrength.STRONG if confidence > 0.75 else SignalStrength.MODERATE,
                        entry_price=price,
                        stop_loss=period_low + atr * 0.5,
                        take_profit=price - atr * 3,
                        confidence=confidence,
                        reasoning=(
                            f"Breakdown below {self.LOOKBACK}-period low={period_low:.4f} "
                            f"volume={last_volume:.0f}"
                        ),
                    )
                )

        return signals
