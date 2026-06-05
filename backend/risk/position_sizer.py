"""Kelly-adjusted fixed-fractional position sizer."""
from __future__ import annotations

from core.state import PositionSize, TradingSignal


class PositionSizer:
    def __init__(self, risk_per_trade: float = 0.005, base_currency: str = "USDT"):
        self.risk_per_trade = risk_per_trade
        self.base_currency = base_currency

    def calculate(
        self,
        signal: TradingSignal,
        equity: float,
        current_price: float,
    ) -> PositionSize:
        """Fixed-fractional sizing adjusted by signal confidence."""
        adjusted_risk = self.risk_per_trade * signal.confidence
        risk_amount = equity * adjusted_risk

        stop_distance = abs(signal.entry_price - signal.stop_loss)
        if stop_distance <= 0 or current_price <= 0:
            return PositionSize(
                symbol=signal.symbol,
                signal=signal,
                size_usd=0,
                size_units=0,
                risk_amount=0,
                risk_pct=0,
            )

        size_units = risk_amount / stop_distance
        size_usd = size_units * current_price

        # Cap position at 20% of equity
        max_usd = equity * 0.20
        if size_usd > max_usd:
            size_usd = max_usd
            # current_price already validated > 0 above
            size_units = size_usd / current_price if current_price > 0 else 0.0

        return PositionSize(
            symbol=signal.symbol,
            signal=signal,
            size_usd=size_usd,
            size_units=size_units,
            risk_amount=risk_amount,
            risk_pct=adjusted_risk,
        )
