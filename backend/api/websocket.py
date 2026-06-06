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
_AUTH_TIMEOUT_SEC = 10


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    def add(self, ws: WebSocket) -> bool:
        if len(self.active) >= MAX_CONNECTIONS:
            return False
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
    # Accept first so we can send a proper close frame on auth failure.
    await ws.accept()

    # ── In-message auth (first frame must carry the API key) ──────────────────
    # Using the first message avoids the key appearing in server access logs,
    # which would happen with query-param auth.
    try:
        raw_auth = await asyncio.wait_for(ws.receive_text(), timeout=_AUTH_TIMEOUT_SEC)
        auth_msg = json.loads(raw_auth)
        api_key = auth_msg.get("api_key", "")
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not settings.api_key or api_key != settings.api_key:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not manager.add(ws):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
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
