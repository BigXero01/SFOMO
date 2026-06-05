"""Kill switch — halts all trading when drawdown limit is breached."""
from __future__ import annotations

from loguru import logger


class KillSwitch:
    def __init__(self, max_drawdown: float = 0.15):
        self.max_drawdown = max_drawdown
        self._triggered = False

    def should_trigger(self, current_drawdown: float) -> bool:
        if self._triggered:
            return True
        if current_drawdown >= self.max_drawdown:
            self._triggered = True
            logger.critical(
                f"[KillSwitch] TRIGGERED: drawdown={current_drawdown:.2%} >= "
                f"limit={self.max_drawdown:.2%}"
            )
            return True
        return False

    def reset(self) -> None:
        """Manual reset — requires explicit operator action."""
        self._triggered = False
        logger.warning("[KillSwitch] Reset by operator")

    @property
    def is_triggered(self) -> bool:
        return self._triggered
