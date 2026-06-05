"""Signal endpoints — trigger cycles and view current signals."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/signals", tags=["signals"])

_last_cycle_state = None


class CycleRequest(BaseModel):
    symbols: Optional[List[str]] = None
    timeframe: Optional[str] = None


@router.post("/run-cycle")
async def run_cycle(request: CycleRequest, background_tasks: BackgroundTasks):
    """Trigger one trading cycle asynchronously."""
    global _last_cycle_state
    try:
        from core.graph import run_trading_cycle
        background_tasks.add_task(
            _run_and_store,
            request.symbols,
            request.timeframe,
        )
        return {"status": "cycle_started", "symbols": request.symbols}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/last-cycle")
async def get_last_cycle():
    if _last_cycle_state is None:
        return {"message": "No cycle run yet"}
    return {
        "cycle_id": _last_cycle_state.cycle_id,
        "regime": _last_cycle_state.market_regime.value,
        "raw_signals": len(_last_cycle_state.raw_signals),
        "filtered_signals": len(_last_cycle_state.filtered_signals),
        "executed_orders": len(_last_cycle_state.executed_orders),
        "kill_switch": _last_cycle_state.kill_switch,
        "errors": _last_cycle_state.errors,
        "messages": _last_cycle_state.agent_messages,
        "strategy_weights": _last_cycle_state.strategy_weights,
        "signals": [s.model_dump() for s in _last_cycle_state.filtered_signals],
    }


async def _run_and_store(symbols, timeframe):
    global _last_cycle_state
    from core.graph import run_trading_cycle
    _last_cycle_state = await run_trading_cycle(symbols=symbols, timeframe=timeframe)
