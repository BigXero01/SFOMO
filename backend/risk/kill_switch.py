"""Kill switch — halts all trading when drawdown limit is breached.

State is stored in Redis so it survives restarts and is shared across workers.
An operator must explicitly call reset() to re-enable trading after a trigger.
"""
from __future__ import annotations

import redis.asyncio as aioredis
from loguru import logger

REDIS_KEY = "sfomo:kill_switch:triggered"


class KillSwitch:
    def __init__(self, redis_url: str, max_drawdown: float = 0.15):
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self.max_drawdown = max_drawdown

    async def should_trigger(self, current_drawdown: float) -> bool:
        # Always check persistent state first — survives restarts.
        if await self._redis.get(REDIS_KEY):
            logger.warning("[KillSwitch] Still triggered from previous session")
            return True
        if current_drawdown >= self.max_drawdown:
            await self._redis.set(REDIS_KEY, "1")
            logger.critical(
                f"[KillSwitch] TRIGGERED: drawdown={current_drawdown:.2%} >= "
                f"limit={self.max_drawdown:.2%}"
            )
            return True
        return False

    async def reset(self) -> None:
        """Explicit operator reset — removes persistent trigger flag."""
        await self._redis.delete(REDIS_KEY)
        logger.warning("[KillSwitch] Reset by operator")

    async def is_triggered(self) -> bool:
        return bool(await self._redis.get(REDIS_KEY))

    async def close(self) -> None:
        await self._redis.aclose()
