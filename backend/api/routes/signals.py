"""Signal endpoints — trigger cycles and view current signals."""
from __future__ import annotations

import asyncio
import copy
import re
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import Field, field_validator
from pydantic import BaseModel

from api.auth import require_api_key

router = APIRouter(prefix="/signals", tags=["signals"])

# ── Rate limiting (1 cycle/5 min per IP, 200 reads/hour) ──────────────────────
_cycle_locks: dict[str, asyncio.Lock] = {}
_cycle_timestamps: dict[str, float] = {}
CYCLE_COOLDOWN_SECS = 300  # 5 minutes per IP

# ── Thread-safe cycle state ────────────────────────────────────────────────────
_state_lock = asyncio.Lock()
_last_cycle_state = None

_VALID_TIMEFRAMES = re.compile(r"^(1|3|5|15|30)m$|^(1|2|4|6|8|12)h$|^1d$|^1w$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,10}/[A-Z]{2,10}$")


class CycleRequest(BaseModel):
    symbols: Optional[List[str]] = Field(None, min_length=1, max_length=10)
    timeframe: Optional[str] = Field(None, max_length=4)

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        for s in v:
            if not _SYMBOL_RE.match(s):
                raise ValueError(f"Invalid symbol format: {s!r}")
        return v

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _VALID_TIMEFRAMES.match(v):
            raise ValueError(f"Invalid timeframe: {v!r}")
        return v


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/run-cycle", dependencies=[Depends(require_api_key)])
async def run_cycle(
    request: Request,
    body: CycleRequest,
    background_tasks: BackgroundTasks,
):
    """Trigger one trading cycle — rate-limited to 1 per 5 minutes per client."""
    import time

    ip = _client_ip(request)
    now = time.monotonic()
    last = _cycle_timestamps.get(ip, 0)
    if now - last < CYCLE_COOLDOWN_SECS:
        wait = int(CYCLE_COOLDOWN_SECS - (now - last))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit: wait {wait}s before next cycle",
        )
    _cycle_timestamps[ip] = now

    background_tasks.add_task(_run_and_store, body.symbols, body.timeframe)
    return {"status": "cycle_started", "symbols": body.symbols}


@router.get("/last-cycle", dependencies=[Depends(require_api_key)])
async def get_last_cycle():
    async with _state_lock:
        state = copy.copy(_last_cycle_state)

    if state is None:
        return {"message": "No cycle run yet"}

    return {
        "cycle_id": state.cycle_id,
        "regime": state.market_regime.value,
        "raw_signals": len(state.raw_signals),
        "filtered_signals": len(state.filtered_signals),
        "executed_orders": len(state.executed_orders),
        "kill_switch": state.kill_switch,
        "errors": state.errors,
        "messages": state.agent_messages,
        "strategy_weights": state.strategy_weights,
        "signals": [s.model_dump() for s in state.filtered_signals],
    }


async def _run_and_store(symbols: Optional[List[str]], timeframe: Optional[str]) -> None:
    global _last_cycle_state
    from core.graph import run_trading_cycle

    result = await run_trading_cycle(symbols=symbols, timeframe=timeframe)
    async with _state_lock:
        _last_cycle_state = result
