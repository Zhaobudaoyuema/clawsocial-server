"""WebSocket endpoint for Mac Worker (Ollama proxy)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/worker")
async def ws_worker(websocket: WebSocket) -> None:
    await websocket.accept()
    app = websocket.app
    worker_router = app.state.worker_router
    await worker_router.attach(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            await worker_router.handle_message(raw)
    except WebSocketDisconnect:
        logger.info("worker disconnected")
    finally:
        await worker_router.detach(websocket)
