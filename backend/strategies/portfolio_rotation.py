"""Portfolio Rotation — rank assets by momentum score, rotate into leaders."""
from __future__ import annotations

from typing import Any, Dict, List

from core.state import SignalDirection, SignalStrength, TradingSignal
from strategies.base import BaseStrategy


class PortfolioRotationStrategy(BaseStrategy):
    """Rotate capital into top-performing assets by risk-adjusted momentum."""

    MOMENTUM_PERIOD = 20
    TOP_N = 2

    async def generate_signals(
        self,
        candles: Dict[str, Any],
        order_books: Dict[str, Any],
        market_structure: Dict[str, Any],
        funding_rates: Dict[str, float],
    ) -> List[TradingSignal]:
        scores: Dict[str, float] = {}

        for symbol, data in candles.items():
            closes = data.get("close", [])
            highs = data.get("high", [])
            lows = data.get("low", [])

            if len(closes) < self.MOMENTUM_PERIOD + 2:
                continue

            price = closes[-1]
            start_price = closes[-self.MOMENTUM_PERIOD - 1]
            if start_price <= 0:
                continue

            momentum = (price - start_price) / start_price
            atr = self._compute_atr(highs, lows, closes)
            vol_adj_momentum = momentum / (atr / price) if atr > 0 else momentum
            scores[symbol] = vol_adj_momentum

        if not scores:
            return []

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[: self.TOP_N]]
        bottom_symbols = [s for s, _ in ranked[-self.TOP_N:] if scores[s] < 0]

        signals: List[TradingSignal] = []

        for symbol in top_symbols:
            data = candles.get(symbol, {})
            closes = data.get("close", [])
            highs = data.get("high", [])
            lows = data.get("low", [])

            if len(closes) < 3:
                continue

            price = closes[-1]
            atr = self._compute_atr(highs, lows, closes) if highs and lows else price * 0.02
            score = scores[symbol]
            confidence = min(0.80, 0.55 + abs(score) * 0.5)

            signals.append(
                TradingSignal(
                    symbol=symbol,
                    strategy="portfolio_rotation",
                    direction=SignalDirection.LONG,
                    strength=SignalStrength.MODERATE,
                    entry_price=price,
                    stop_loss=price - atr * 2,
                    take_profit=price + atr * 3,
                    confidence=confidence,
                    reasoning=f"Top momentum score={score:.3f} (rank #{top_symbols.index(symbol)+1})",
                )
            )

        return signals
