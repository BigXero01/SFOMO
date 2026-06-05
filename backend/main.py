"""SFOMO — AI Agent Trading Bot — FastAPI entry point."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import text

from api.auth import require_api_key
from api.routes import portfolio_router, signals_router, trades_router
from api.websocket import websocket_endpoint
from config import get_settings
from services.database import AsyncSessionLocal, DatabaseService
from services.vector_store import VectorStoreService

settings = get_settings()

_scheduler_task: asyncio.Task | None = None


async def _trading_scheduler() -> None:
    """Run a trading cycle on a fixed cadence."""
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
        except Exception as exc:
            logger.error(f"[Scheduler] cycle error: {exc}", exc_info=True)

        interval = 3600 if settings.is_production else 300
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task

    logger.info("SFOMO starting up...")

    try:
        db = DatabaseService()
        await db.initialize()
        logger.info("Database schema initialized")
    except Exception as exc:
        logger.warning(f"DB init warning: {exc}")

    try:
        vs = VectorStoreService()
        await vs.ensure_collections()
        await vs.close()
        logger.info("Vector store initialized")
    except Exception as exc:
        logger.warning(f"Vector store init warning: {exc}")

    if settings.app_env != "test":
        _scheduler_task = asyncio.create_task(_trading_scheduler())
        logger.info("Trading scheduler started")

    yield

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
    # Hide schema endpoints in production to reduce attack surface
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# ── CORS: exact origins only, explicit methods ─────────────────────────────────
_allowed_origins = ["http://localhost:3000"]
if settings.is_production:
    _allowed_origins = ["https://app.sfomo.app"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)


# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        f"{request.method} {request.url.path} "
        f"status={response.status_code} "
        f"duration={duration_ms:.1f}ms "
        f"ip={request.client.host if request.client else 'unknown'}"
    )
    return response


# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(portfolio_router, prefix="/api/v1")
app.include_router(signals_router, prefix="/api/v1")
app.include_router(trades_router, prefix="/api/v1")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket_endpoint(websocket)


# ── Kill switch admin endpoint (auth required) ────────────────────────────────
@app.post("/api/v1/admin/kill-switch/reset")
async def reset_kill_switch(_: str = require_api_key):
    """Operator endpoint to re-enable trading after kill switch fires."""
    from risk.kill_switch import KillSwitch

    ks = KillSwitch(redis_url=settings.redis_url, max_drawdown=settings.max_portfolio_drawdown)
    await ks.reset()
    await ks.close()
    logger.warning("[Admin] Kill switch manually reset")
    return {"status": "kill_switch_reset"}


# ── Health check with real DB connectivity probe ───────────────────────────────
@app.get("/health")
async def health():
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"

    overall = "ok" if db_status == "ok" else "degraded"
    status_code = 200 if overall == "ok" else 503

    body = {
        "status": overall,
        "version": "1.0.0",
        "env": settings.app_env,
        "exchange": settings.exchange_id,
        "sandbox": settings.exchange_sandbox,
        "database": db_status,
    }

    from fastapi.responses import JSONResponse
    return JSONResponse(content=body, status_code=status_code)


@app.get("/")
async def root():
    return {"name": "SFOMO — AI Agent Trading Bot", "health": "/health"}
