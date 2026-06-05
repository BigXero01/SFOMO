"""Portfolio endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.database import DatabaseService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/snapshot")
async def get_portfolio_snapshot():
    db = DatabaseService()
    snapshot = await db.get_portfolio_snapshot()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No portfolio data yet")
    return snapshot.model_dump()


@router.get("/history")
async def get_portfolio_history(limit: int = 100):
    db = DatabaseService()
    from sqlalchemy import text
    from services.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT * FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        rows = [dict(r) for r in result.mappings()]
    return {"history": rows}


@router.get("/performance")
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
        "avg_win": sum(t["pnl"] for t in wins) / len(wins) if wins else 0,
        "avg_loss": sum(t["pnl"] for t in losses) / len(losses) if losses else 0,
    }
