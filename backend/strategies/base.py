"""Base strategy interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from core.state import TradingSignal


class BaseStrategy(ABC):
    def __init__(self, weight: float = 1.0):
        self.weight = weight
        self.name = self.__class__.__name__

    @abstractmethod
    async def generate_signals(
        self,
        candles: Dict[str, Any],
        order_books: Dict[str, Any],
        market_structure: Dict[str, Any],
        funding_rates: Dict[str, float],
    ) -> List[TradingSignal]:
        """Generate trading signals from market data."""
        ...

    def _compute_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """Average True Range."""
        if len(highs) < period + 1:
            return 0.0
        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            true_ranges.append(tr)
        return sum(true_ranges[-period:]) / period

    def _compute_rsi(self, closes: List[float], period: int = 14) -> float:
        """Relative Strength Index."""
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d for d in deltas[-period:] if d > 0]
        losses = [-d for d in deltas[-period:] if d < 0]
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _compute_ema(self, closes: List[float], period: int) -> float:
        """Exponential Moving Average — seeded from SMA for warm-up accuracy."""
        if len(closes) < period * 2:
            return closes[-1] if closes else 0.0
        k = 2 / (period + 1)
        # Seed from SMA of the first `period` bars instead of closes[0]
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    def _compute_sma(self, closes: List[float], period: int) -> float:
        if len(closes) < period:
            return closes[-1] if closes else 0.0
        return sum(closes[-period:]) / period
