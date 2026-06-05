"""SFOMO — AI Agent Trading Bot — FastAPI entry point."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.routes import portfolio_router, signals_router, trades_router
from api.websocket import websocket_endpoint
from config import get_settings
from services.database import DatabaseService
from services.vector_store import VectorStoreService

settings = get_settings()

# ── Scheduler ─────────────────────────────────────────────────────────────────
_scheduler_task: asyncio.Task | None = None


async def _trading_scheduler():
    """Run a trading cycle every hour (production cadence)."""
    from core.graph import run_trading_cycle
    while True:
        try:
            logger.info("[Scheduler] Starting trading cycle...")
            state = await run_trading_cycle()
            logger.info(
                f"[Scheduler] Cycle {state.cycle_id} complete | "
                f"regime={state.market_regime.value} | "
                f"executed={len(state.executed_orders)}"
            )
        except Exception as e:
            logger.error(f"[Scheduler] cycle error: {e}")

        interval = 3600 if settings.is_production else 300  # 1h prod, 5m dev
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task

    logger.info("SFOMO starting up...")

    # Initialize DB schema
    try:
        db = DatabaseService()
        await db.initialize()
        logger.info("Database schema initialized")
    except Exception as e:
        logger.warning(f"DB init warning: {e}")

    # Initialize Qdrant collections
    try:
        vs = VectorStoreService()
        await vs.ensure_collections()
        await vs.close()
        logger.info("Vector store initialized")
    except Exception as e:
        logger.warning(f"Vector store init warning: {e}")

    # Start trading scheduler
    if settings.app_env != "test":
        _scheduler_task = asyncio.create_task(_trading_scheduler())
        logger.info("Trading scheduler started")

    yield

    # Cleanup
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("SFOMO shutdown complete")


app = FastAPI(
    title="SFOMO — AI Agent Trading Bot",
    description="Institutional-style crypto asset management via multi-agent AI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.sfomo.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(portfolio_router, prefix="/api/v1")
app.include_router(signals_router, prefix="/api/v1")
app.include_router(trades_router, prefix="/api/v1")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_endpoint(websocket)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "env": settings.app_env,
        "exchange": settings.exchange_id,
        "sandbox": settings.exchange_sandbox,
    }


@app.get("/")
async def root():
    return {
        "name": "SFOMO — AI Agent Trading Bot",
        "docs": "/docs",
        "health": "/health",
    }
