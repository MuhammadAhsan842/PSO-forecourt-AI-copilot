"""WebSocket live event feed.

Kept intentionally tiny: a set of connected clients + a broadcast helper the
routes call after each event write. If a client falls behind, its send fails and
it is dropped; the pipeline never blocks on a slow browser.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.common.logging import get_logger
from src.common.types import EventRecord

log = get_logger(__name__)

_clients: set[WebSocket] = set()
_lock = asyncio.Lock()


async def broadcast_event(event: EventRecord) -> None:
    payload = event.model_dump(mode="json")
    dead: list[WebSocket] = []
    async with _lock:
        for ws in _clients:
            try:
                await ws.send_json({"type": "event", "data": payload})
            except Exception:
                dead.append(ws)
        for ws in dead:
            _clients.discard(ws)


def register_websocket(app: FastAPI, path: str = "/ws/events") -> None:
    @app.websocket(path)
    async def _feed(ws: WebSocket) -> None:
        await ws.accept()
        async with _lock:
            _clients.add(ws)
        log.info("ws_client_connected", extra={"context": {"path": path}})
        try:
            await ws.send_json({"type": "hello", "data": {"clients": len(_clients)}})
            while True:
                # Keep the socket open; we only push messages, but we still read to
                # detect disconnects.
                _ = await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            log.warning("ws_error", extra={"context": {"err": str(exc)}})
        finally:
            async with _lock:
                _clients.discard(ws)


async def client_count() -> int:
    async with _lock:
        return len(_clients)


__all__ = ["broadcast_event", "client_count", "register_websocket"]


# Small no-op reference to silence unused-import complaints in typecheckers that
# don't see the runtime binding pattern used above.
_ = Any
