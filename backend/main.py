"""SFOMO — AI Agent Trading Bot — FastAPI entry point."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi import Security
from loguru import logger
from sqlalchemy import text

from api.routes import funds_router, portfolio_router, signals_router, trades_router
from api.terminal import terminal_websocket_endpoint
from api.websocket import websocket_endpoint
from config import get_settings
from services.database import AsyncSessionLocal, DatabaseService
from services.vector_store import VectorStoreService

settings = get_settings()

_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def _require_admin_key(admin_key: str | None = Security(_admin_key_header)) -> str:
    """Separate high-privilege key for destructive admin operations."""
    configured = settings.admin_key
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_KEY not configured",
        )
    if not admin_key or admin_key != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin key",
        )
    return admin_key


@asynccontextmanager
async def lifespan(app: FastAPI):
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
        from core.scheduler import get_scheduler
        get_scheduler().start()
        logger.info("Trading scheduler started")

    yield

    if settings.app_env != "test":
        from core.scheduler import get_scheduler
        get_scheduler().stop()

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

# ── CORS: driven by CORS_ORIGINS env var (comma-separated) ────────────────────
# Local:   CORS_ORIGINS=http://localhost:3000
# Railway: CORS_ORIGINS=https://your-frontend.up.railway.app
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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
    # Log path only (not query string) to avoid leaking API keys in access logs
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
app.include_router(funds_router, prefix="/api/v1")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket_endpoint(websocket)


@app.websocket("/ws/terminal")
async def ws_terminal_endpoint(websocket: WebSocket) -> None:
    await terminal_websocket_endpoint(websocket)


# ── Kill switch admin endpoint ─────────────────────────────────────────────────
# Requires ADMIN_KEY — a separate, higher-privilege credential distinct from API_KEY.
# This prevents an API key compromise from allowing kill-switch reset.
@app.post("/api/v1/admin/kill-switch/reset")
async def reset_kill_switch(_: str = Security(_require_admin_key)):
    """Operator endpoint to re-enable trading after kill switch fires."""
    from risk.kill_switch import KillSwitch

    ks = KillSwitch(max_drawdown=settings.max_portfolio_drawdown)
    await ks.reset()
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
