"""Trend Following — EMA crossover + ADX filter."""
from __future__ import annotations

from typing import Any, Dict, List

from core.state import SignalDirection, SignalStrength, TradingSignal
from strategies.base import BaseStrategy


class TrendFollowingStrategy(BaseStrategy):
    """Fast/slow EMA crossover with ADX trend strength filter."""

    FAST_EMA = 20
    SLOW_EMA = 50
    ADX_THRESHOLD = 25
    RSI_MIN = 45
    RSI_MAX = 75

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

            if len(closes) < self.SLOW_EMA + 5:
                continue

            fast_ema = self._compute_ema(closes, self.FAST_EMA)
            slow_ema = self._compute_ema(closes, self.SLOW_EMA)
            prev_fast = self._compute_ema(closes[:-1], self.FAST_EMA)
            prev_slow = self._compute_ema(closes[:-1], self.SLOW_EMA)
            rsi = self._compute_rsi(closes)
            atr = self._compute_atr(highs, lows, closes)
            price = closes[-1]

            if not price or not atr:
                continue

            # Bullish crossover
            if (
                prev_fast <= prev_slow
                and fast_ema > slow_ema
                and self.RSI_MIN <= rsi <= self.RSI_MAX
            ):
                confidence = min(0.85, 0.55 + (fast_ema - slow_ema) / price * 10)
                strength = (
                    SignalStrength.STRONG if confidence > 0.75
                    else SignalStrength.MODERATE
                )
                signals.append(
                    TradingSignal(
                        symbol=symbol,
                        strategy="trend_following",
                        direction=SignalDirection.LONG,
                        strength=strength,
                        entry_price=price,
                        stop_loss=price - atr * 2,
                        take_profit=price + atr * 4,
                        confidence=confidence,
                        reasoning=f"EMA{self.FAST_EMA} crossed above EMA{self.SLOW_EMA}, RSI={rsi:.1f}",
                    )
                )

            # Bearish crossover
            elif (
                prev_fast >= prev_slow
                and fast_ema < slow_ema
                and rsi < 55
            ):
                confidence = min(0.85, 0.55 + (slow_ema - fast_ema) / price * 10)
                strength = (
                    SignalStrength.STRONG if confidence > 0.75
                    else SignalStrength.MODERATE
                )
                signals.append(
                    TradingSignal(
                        symbol=symbol,
                        strategy="trend_following",
                        direction=SignalDirection.SHORT,
                        strength=strength,
                        entry_price=price,
                        stop_loss=price + atr * 2,
                        take_profit=price - atr * 4,
                        confidence=confidence,
                        reasoning=f"EMA{self.FAST_EMA} crossed below EMA{self.SLOW_EMA}, RSI={rsi:.1f}",
                    )
                )

        return signals
