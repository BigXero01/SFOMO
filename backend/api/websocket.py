"""WebSocket endpoint — streams real-time portfolio and signal updates."""
from __future__ import annotations

import asyncio
import json
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from services.redis_service import (
    STREAM_ALERTS,
    STREAM_ORDERS,
    STREAM_PORTFOLIO,
    STREAM_SIGNALS,
    RedisService,
)


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, message: dict) -> None:
        dead = set()
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.active -= dead


manager = ConnectionManager()


async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    redis = RedisService()
    last_ids = {
        STREAM_SIGNALS: "$",
        STREAM_ORDERS: "$",
        STREAM_PORTFOLIO: "$",
        STREAM_ALERTS: "$",
    }
    try:
        while True:
            for stream, last_id in list(last_ids.items()):
                entries = await redis._redis.xread({stream: last_id}, count=10, block=100)
                for stream_name, messages in entries:
                    for msg_id, fields in messages:
                        last_ids[stream] = msg_id
                        payload = {
                            "stream": stream_name,
                            "id": msg_id,
                        }
                        try:
                            payload["data"] = json.loads(fields.get("data", "{}"))
                        except Exception:
                            payload["data"] = dict(fields)
                        await ws.send_json(payload)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        logger.error(f"[WebSocket] error: {e}")
        manager.disconnect(ws)
    finally:
        await redis.close()
