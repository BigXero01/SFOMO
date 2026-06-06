"""CCXT exchange service — unified interface for all supported exchanges."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings

settings = get_settings()


class ExchangeService:
    """Async CCXT wrapper with retry logic and sandbox support."""

    def __init__(self, exchange_id: Optional[str] = None):
        eid = exchange_id or settings.exchange_id
        exchange_class = getattr(ccxt, eid)
        self._exchange: ccxt.Exchange = exchange_class(
            {
                "apiKey": settings.exchange_api_key,
                "secret": settings.exchange_api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        if settings.exchange_sandbox:
            self._exchange.set_sandbox_mode(True)

    async def close(self) -> None:
        await self._exchange.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> Dict[str, List]:
        """Fetch OHLCV candles and return as named columns."""
        raw = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not raw:
            return {}
        timestamps, opens, highs, lows, closes, volumes = zip(*raw)
        return {
            "timestamp": list(timestamps),
            "open": list(opens),
            "high": list(highs),
            "low": list(lows),
            "close": list(closes),
            "volume": list(volumes),
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        return await self._exchange.fetch_order_book(symbol, limit=limit)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        return await self._exchange.fetch_ticker(symbol)

    async def fetch_funding_rate(self, symbol: str) -> float:
        """Fetch perpetual funding rate (returns 0.0 for spot markets)."""
        try:
            if self._exchange.has.get("fetchFundingRate"):
                data = await self._exchange.fetch_funding_rate(symbol)
                return float(data.get("fundingRate", 0.0))
        except Exception:
            pass
        return 0.0

    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest (returns 0.0 for spot markets)."""
        try:
            if self._exchange.has.get("fetchOpenInterest"):
                data = await self._exchange.fetch_open_interest(symbol)
                return float(data.get("openInterestAmount", 0.0))
        except Exception:
            pass
        return 0.0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        logger.info(
            f"[Exchange] {order_type.upper()} {side.upper()} {amount:.6f} {symbol}"
            + (f" @ {price}" if price else "")
        )
        return await self._exchange.create_order(
            symbol, order_type, side, amount, price, params or {}
        )

    async def fetch_balance(self) -> Dict[str, Any]:
        return await self._exchange.fetch_balance()

    async def fetch_positions(self) -> List[Dict[str, Any]]:
        try:
            if self._exchange.has.get("fetchPositions"):
                return await self._exchange.fetch_positions()
        except Exception:
            pass
        return []

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return await self._exchange.cancel_order(order_id, symbol)

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._exchange.fetch_open_orders(symbol)

    # ── Deposits & Withdrawals ────────────────────────────────────────────

    async def fetch_deposit_address(
        self, currency: str, network: Optional[str] = None
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if network:
            params["network"] = network
        return await self._exchange.fetch_deposit_address(currency, params)

    async def fetch_deposits(
        self, currency: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        try:
            if self._exchange.has.get("fetchDeposits"):
                return await self._exchange.fetch_deposits(currency, limit=limit) or []
        except Exception as exc:
            logger.warning(f"[Exchange] fetch_deposits error: {exc}")
        return []

    async def withdraw(
        self,
        currency: str,
        amount: float,
        address: str,
        tag: Optional[str] = None,
        network: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if network:
            params["network"] = network
        logger.warning(
            f"[Exchange] WITHDRAWAL {amount} {currency} → {address[:16]}... net={network}"
        )
        return await self._exchange.withdraw(currency, amount, address, tag, params)

    async def fetch_withdrawals(
        self, currency: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        try:
            if self._exchange.has.get("fetchWithdrawals"):
                return await self._exchange.fetch_withdrawals(currency, limit=limit) or []
        except Exception as exc:
            logger.warning(f"[Exchange] fetch_withdrawals error: {exc}")
        return []
