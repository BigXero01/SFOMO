"""Trade history and signal endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from services.database import DatabaseService

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/recent")
async def get_recent_trades(limit: int = Query(50, le=500)):
    db = DatabaseService()
    trades = await db.get_recent_trades(limit=limit)
    return {"trades": trades, "count": len(trades)}


@router.get("/by-strategy")
async def get_trades_by_strategy():
    db = DatabaseService()
    trades = await db.get_recent_trades(limit=500)
    by_strategy: dict = {}
    for t in trades:
        s = t.get("strategy", "unknown")
        if s not in by_strategy:
            by_strategy[s] = []
        by_strategy[s].append(t)
    return by_strategy
