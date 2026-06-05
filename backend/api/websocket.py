"""WebSocket endpoint — streams real-time portfolio and signal updates."""
from __future__ import annotations

import asyncio
import json
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect, status
from loguru import logger

from config import get_settings
from services.redis_service import (
    STREAM_ALERTS,
    STREAM_ORDERS,
    STREAM_PORTFOLIO,
    STREAM_SIGNALS,
    RedisService,
)

settings = get_settings()

# Max session: 4 hours (100ms tick × 144 000 = 14 400s)
MAX_WS_ITERATIONS = 144_000
MAX_CONNECTIONS = 50


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> bool:
        if len(self.active) >= MAX_CONNECTIONS:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return False
        await ws.accept()
        self.active.add(ws)
        return True

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, message: dict) -> None:
        dead = set()
        for ws in self.active:
            try:
                await ws.send_json(message)
            except (WebSocketDisconnect, RuntimeError):
                dead.add(ws)
        self.active -= dead


manager = ConnectionManager()


async def websocket_endpoint(ws: WebSocket) -> None:
    # ── API key auth via query param for WS (headers not reliable in browsers) ──
    api_key = ws.query_params.get("api_key")
    if not settings.api_key or api_key != settings.api_key:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    accepted = await manager.connect(ws)
    if not accepted:
        logger.warning("[WebSocket] connection refused — max connections reached")
        return

    redis = RedisService()
    last_ids = {
        STREAM_SIGNALS: "$",
        STREAM_ORDERS: "$",
        STREAM_PORTFOLIO: "$",
        STREAM_ALERTS: "$",
    }
    iterations = 0

    try:
        while iterations < MAX_WS_ITERATIONS:
            for stream in list(last_ids):
                try:
                    entries = await redis._redis.xread(
                        {stream: last_ids[stream]}, count=10, block=100
                    )
                except Exception as exc:
                    logger.warning(f"[WebSocket] redis read error on {stream}: {exc}")
                    continue

                for stream_name, messages in entries:
                    for msg_id, fields in messages:
                        last_ids[stream] = msg_id
                        payload: dict = {"stream": stream_name, "id": msg_id}
                        try:
                            payload["data"] = json.loads(fields.get("data", "{}"))
                        except json.JSONDecodeError:
                            payload["data"] = {k: v for k, v in fields.items()}
                        try:
                            await ws.send_json(payload)
                        except (WebSocketDisconnect, RuntimeError):
                            return

            await asyncio.sleep(0.1)
            iterations += 1

        # Clean session timeout
        await ws.close(code=status.WS_1000_NORMAL_CLOSURE)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"[WebSocket] unexpected error: {exc}", exc_info=True)
    finally:
        manager.disconnect(ws)
        await redis.close()
