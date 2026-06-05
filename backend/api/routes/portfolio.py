"""Portfolio endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from api.auth import require_api_key
from services.database import AsyncSessionLocal, DatabaseService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/snapshot", dependencies=[Depends(require_api_key)])
async def get_portfolio_snapshot():
    db = DatabaseService()
    snapshot = await db.get_portfolio_snapshot()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No portfolio data yet")
    return snapshot.model_dump()


@router.get("/history", dependencies=[Depends(require_api_key)])
async def get_portfolio_history(limit: int = Query(100, ge=1, le=10_000)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT * FROM portfolio_snapshots "
                "ORDER BY snapshot_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        rows = [dict(r) for r in result.mappings()]
    return {"history": rows}


@router.get("/performance", dependencies=[Depends(require_api_key)])
async def get_performance():
    db = DatabaseService()
    trades = await db.get_recent_trades(limit=500)
    if not trades:
        return {"message": "No trades recorded yet"}

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) < 0]
    total_pnl = sum(t.get("pnl", 0) for t in trades)

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "total_pnl": total_pnl,
        # Use .get() consistently — schema may have NULL pnl rows
        "avg_win": sum(t.get("pnl", 0) for t in wins) / len(wins) if wins else 0,
        "avg_loss": sum(t.get("pnl", 0) for t in losses) / len(losses) if losses else 0,
    }
