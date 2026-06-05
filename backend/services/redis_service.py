"""Redis Streams service — event bus for inter-agent messaging."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from loguru import logger

from config import get_settings

settings = get_settings()

STREAM_SIGNALS = "sfomo:signals"
STREAM_ORDERS = "sfomo:orders"
STREAM_PORTFOLIO = "sfomo:portfolio"
STREAM_ALERTS = "sfomo:alerts"


class RedisService:
    def __init__(self):
        self._redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def publish_signal(self, signal_data: Dict[str, Any]) -> str:
        return await self._redis.xadd(
            STREAM_SIGNALS,
            {"data": json.dumps(signal_data, default=str)},
            maxlen=10_000,
        )

    async def publish_order(self, order_data: Dict[str, Any]) -> str:
        return await self._redis.xadd(
            STREAM_ORDERS,
            {"data": json.dumps(order_data, default=str)},
            maxlen=10_000,
        )

    async def publish_portfolio(self, portfolio_data: Dict[str, Any]) -> str:
        return await self._redis.xadd(
            STREAM_PORTFOLIO,
            {"data": json.dumps(portfolio_data, default=str)},
            maxlen=1_000,
        )

    async def publish_alert(self, level: str, message: str) -> str:
        return await self._redis.xadd(
            STREAM_ALERTS,
            {"level": level, "message": message},
            maxlen=5_000,
        )

    async def read_latest(
        self, stream: str, count: int = 50, last_id: str = "0"
    ) -> List[Dict[str, Any]]:
        entries = await self._redis.xrevrange(stream, count=count)
        results = []
        for entry_id, fields in entries:
            try:
                data = json.loads(fields.get("data", "{}"))
                data["_id"] = entry_id
                results.append(data)
            except Exception:
                pass
        return results

    async def set_cache(self, key: str, value: Any, ttl: int = 300) -> None:
        await self._redis.setex(key, ttl, json.dumps(value, default=str))

    async def get_cache(self, key: str) -> Optional[Any]:
        val = await self._redis.get(key)
        return json.loads(val) if val else None

    async def close(self) -> None:
        await self._redis.aclose()
