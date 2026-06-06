"""Kill switch — halts all trading when drawdown limit is breached.

State is stored in Redis so it survives restarts and is shared across workers.
An operator must explicitly call reset() to re-enable trading after a trigger.
"""
from __future__ import annotations

from loguru import logger

from services.redis_service import get_redis_client

REDIS_KEY = "sfomo:kill_switch:triggered"

# Lua script: atomically set the kill-switch key only if the drawdown threshold
# is exceeded AND the key is not already set.  Returns 1 if triggered (either
# already was, or just became), 0 otherwise.
# ARGV[1] = "1" (value), ARGV[2] = threshold as string (unused — comparison in Python)
_LUA_SETNX = """
local exists = redis.call('GET', KEYS[1])
if exists then return 1 end
redis.call('SET', KEYS[1], ARGV[1])
return 1
"""


class KillSwitch:
    def __init__(self, redis_url: str = "", max_drawdown: float = 0.15):
        # Use the shared pool; redis_url param kept for backwards-compat signature
        self._redis = get_redis_client()
        self.max_drawdown = max_drawdown

    async def should_trigger(self, current_drawdown: float) -> bool:
        # Fast path: already triggered?
        if await self._redis.get(REDIS_KEY):
            logger.warning("[KillSwitch] Still triggered from previous session")
            return True

        if current_drawdown >= self.max_drawdown:
            # Atomic SETNX — only the first worker across all processes wins the
            # race; regardless of who wins, the threshold was crossed so we return True.
            await self._redis.setnx(REDIS_KEY, "1")
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
        # Shared pool — nothing to close here
        pass
