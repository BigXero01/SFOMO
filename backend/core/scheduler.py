"""Production scheduler — singleton service with start/stop/status controls."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from config import get_settings

settings = get_settings()


class SchedulerService:
    """Manages the recurring trading cycle task.

    Singleton — use `get_scheduler()` to obtain the shared instance.
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._interval_secs: int = 3600 if settings.is_production else 300
        self._cycle_count = 0
        self._last_run: Optional[datetime] = None
        self._next_run: Optional[datetime] = None
        self._last_cycle_id: Optional[str] = None
        self._last_error: Optional[str] = None

    # ── Control ──────────────────────────────────────────────────────────────

    def start(self, interval_secs: Optional[int] = None) -> str:
        if self._running:
            return "already_running"
        if interval_secs:
            self._interval_secs = max(60, interval_secs)
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"[Scheduler] started interval={self._interval_secs}s")
        return "started"

    def stop(self) -> str:
        if not self._running:
            return "already_stopped"
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[Scheduler] stopped")
        return "stopped"

    def set_interval(self, secs: int) -> None:
        self._interval_secs = max(60, secs)
        if self._running:
            self.stop()
            self.start()

    # ── Status ───────────────────────────────────────────────────────────────

    def status(self) -> dict:
        now = datetime.now(tz=timezone.utc)
        secs_until_next = None
        if self._next_run and self._running:
            delta = (self._next_run - now).total_seconds()
            secs_until_next = max(0, int(delta))

        return {
            "running": self._running,
            "interval_secs": self._interval_secs,
            "cycle_count": self._cycle_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run": self._next_run.isoformat() if self._next_run else None,
            "secs_until_next": secs_until_next,
            "last_cycle_id": self._last_cycle_id,
            "last_error": self._last_error,
        }

    # ── Internal loop ────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        from core.graph import run_trading_cycle

        while self._running:
            self._last_run = datetime.now(tz=timezone.utc)
            cycle_id = str(uuid.uuid4())[:8]
            logger.info(f"[Scheduler] cycle #{self._cycle_count + 1} starting id={cycle_id}")

            try:
                state = await run_trading_cycle()
                self._cycle_count += 1
                self._last_cycle_id = state.cycle_id
                self._last_error = None
                logger.info(
                    f"[Scheduler] cycle #{self._cycle_count} done "
                    f"regime={state.market_regime.value} "
                    f"executed={len(state.executed_orders)}"
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._last_error = str(exc)
                logger.error(f"[Scheduler] cycle error: {exc}", exc_info=True)

            if not self._running:
                break

            self._next_run = datetime.now(tz=timezone.utc).replace(
                microsecond=0
            )
            # Compute next run timestamp
            from datetime import timedelta
            self._next_run = datetime.now(tz=timezone.utc) + timedelta(
                seconds=self._interval_secs
            )
            try:
                await asyncio.sleep(self._interval_secs)
            except asyncio.CancelledError:
                break


_scheduler: Optional[SchedulerService] = None


def get_scheduler() -> SchedulerService:
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler
