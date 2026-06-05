"""Async PostgreSQL / TimescaleDB service via SQLAlchemy."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import get_settings
from core.state import ExecutedOrder, PortfolioSnapshot

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ── Schema DDL (run once via migrate) ─────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    cycle_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    size DOUBLE PRECISION,
    price DOUBLE PRECISION,
    pnl DOUBLE PRECISION DEFAULT 0,
    strategy TEXT,
    order_id TEXT,
    exchange TEXT,
    fees DOUBLE PRECISION DEFAULT 0,
    slippage_pct DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('trades', 'created_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    total_equity DOUBLE PRECISION,
    cash DOUBLE PRECISION,
    positions_value DOUBLE PRECISION,
    open_positions JSONB DEFAULT '{}',
    unrealized_pnl DOUBLE PRECISION DEFAULT 0,
    realized_pnl DOUBLE PRECISION DEFAULT 0,
    peak_equity DOUBLE PRECISION,
    current_drawdown DOUBLE PRECISION DEFAULT 0,
    snapshot_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('portfolio_snapshots', 'snapshot_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS regime_history (
    id SERIAL PRIMARY KEY,
    cycle_id TEXT,
    regime TEXT,
    confidence DOUBLE PRECISION,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS strategy_weights (
    id SERIAL PRIMARY KEY,
    weights JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cycle_summaries (
    id SERIAL PRIMARY KEY,
    cycle_id TEXT UNIQUE,
    summary JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


class DatabaseService:
    async def _get_session(self) -> AsyncSession:
        return AsyncSessionLocal()

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        async with engine.begin() as conn:
            for stmt in SCHEMA_SQL.split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        await conn.execute(text(stmt))
                    except Exception as e:
                        logger.debug(f"[DB] schema stmt skipped: {e}")

    async def record_trade(self, order: ExecutedOrder, cycle_id: str) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    "INSERT INTO trades "
                    "(cycle_id, symbol, side, size, price, order_id, exchange, fees, slippage_pct) "
                    "VALUES (:cycle_id, :symbol, :side, :size, :price, :order_id, :exchange, :fees, :slippage)"
                ),
                {
                    "cycle_id": cycle_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "size": order.size,
                    "price": order.price,
                    "order_id": order.order_id,
                    "exchange": order.exchange,
                    "fees": order.fees,
                    "slippage": order.slippage_pct,
                },
            )
            await session.commit()

    async def get_portfolio_snapshot(self) -> Optional[PortfolioSnapshot]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT * FROM portfolio_snapshots "
                    "ORDER BY snapshot_at DESC LIMIT 1"
                )
            )
            row = result.mappings().first()
            if not row:
                return None
            return PortfolioSnapshot(
                total_equity=row["total_equity"],
                cash=row["cash"],
                positions_value=row["positions_value"],
                open_positions=row["open_positions"] or {},
                unrealized_pnl=row["unrealized_pnl"],
                realized_pnl=row["realized_pnl"],
                peak_equity=row["peak_equity"],
                current_drawdown=row["current_drawdown"],
            )

    async def save_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    "INSERT INTO portfolio_snapshots "
                    "(total_equity, cash, positions_value, open_positions, "
                    "unrealized_pnl, realized_pnl, peak_equity, current_drawdown) "
                    "VALUES (:equity, :cash, :pos_val, :positions, :upnl, :rpnl, :peak, :dd)"
                ),
                {
                    "equity": snapshot.total_equity,
                    "cash": snapshot.cash,
                    "pos_val": snapshot.positions_value,
                    "positions": json.dumps(snapshot.open_positions),
                    "upnl": snapshot.unrealized_pnl,
                    "rpnl": snapshot.realized_pnl,
                    "peak": snapshot.peak_equity,
                    "dd": snapshot.current_drawdown,
                },
            )
            await session.commit()

    async def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT * FROM trades ORDER BY created_at DESC LIMIT :limit"
                ),
                {"limit": limit},
            )
            return [dict(row) for row in result.mappings()]

    async def record_regime(
        self, regime: str, cycle_id: str, confidence: float
    ) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    "INSERT INTO regime_history (cycle_id, regime, confidence) "
                    "VALUES (:cycle_id, :regime, :confidence)"
                ),
                {"cycle_id": cycle_id, "regime": regime, "confidence": confidence},
            )
            await session.commit()

    async def get_regime_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT * FROM regime_history ORDER BY recorded_at DESC LIMIT :limit"
                ),
                {"limit": limit},
            )
            return [dict(row) for row in result.mappings()]

    async def save_strategy_weights(self, weights: Dict[str, float]) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("INSERT INTO strategy_weights (weights) VALUES (:w)"),
                {"w": json.dumps(weights)},
            )
            await session.commit()
