"""Terminal WebSocket endpoint — streams command output to the browser."""
from __future__ import annotations

import json

from fastapi import WebSocket, WebSocketDisconnect, status
from loguru import logger

from config import get_settings
from core.commands import BANNER, dispatch

settings = get_settings()

MAX_TERMINAL_CONNECTIONS = 10
_active_count = 0


async def terminal_websocket_endpoint(ws: WebSocket) -> None:
    global _active_count

    # Auth via query param (same pattern as /ws)
    api_key = ws.query_params.get("api_key")
    if not settings.api_key or api_key != settings.api_key:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if _active_count >= MAX_TERMINAL_CONNECTIONS:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning("[Terminal] connection refused — max connections reached")
        return

    await ws.accept()
    _active_count += 1
    logger.info(f"[Terminal] client connected (active={_active_count})")

    async def send_line(text: str, style: str) -> None:
        if text == "__CLEAR__":
            await ws.send_text(json.dumps({"t": "clear"}))
        else:
            await ws.send_text(json.dumps({"t": "line", "text": text, "style": style}))

    async def send_prompt() -> None:
        await ws.send_text(json.dumps({"t": "prompt"}))

    try:
        # Send banner on connect
        for text, style in BANNER:
            await send_line(text, style)
        await send_prompt()

        while True:
            raw = await ws.receive_text()

            try:
                msg = json.loads(raw)
                cmd = msg.get("cmd", "").strip()
            except (json.JSONDecodeError, AttributeError):
                cmd = str(raw).strip()

            if not cmd:
                await send_prompt()
                continue

            try:
                async for text, style in dispatch(cmd):
                    await send_line(text, style)
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                logger.error(f"[Terminal] dispatch error: {exc}", exc_info=True)
                await send_line(f"  Internal error: {exc}", "error")

            await send_prompt()

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"[Terminal] unexpected error: {exc}", exc_info=True)
    finally:
        _active_count -= 1
        logger.info(f"[Terminal] client disconnected (active={_active_count})")
