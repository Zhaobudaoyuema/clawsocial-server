"""Route chat/completions requests to connected Mac Worker."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.deid.worker.errors import WorkerBusy, WorkerOffline, WorkerRequestError
from app.deid.worker.session import WorkerSession
from app.deid.worker.sse_parse import parse_ollama_sse_tokens

logger = logging.getLogger(__name__)

_STREAM_DONE = object()


@dataclass
class _StreamPending:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    error: WorkerRequestError | None = None


class WorkerRouter:
    """Single-worker connection pool with pending request futures."""

    def __init__(self) -> None:
        self._session: WorkerSession | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._pending_streams: dict[str, _StreamPending] = {}
        self._lock = asyncio.Lock()

    @property
    def session(self) -> WorkerSession | None:
        return self._session

    def status_dict(self) -> dict:
        if not self._session:
            return {
                "online": False,
                "state": "offline",
                "model": None,
                "hostname": None,
                "version": None,
                "mode": None,
            }
        return self._session.to_status_dict()

    async def attach(self, ws: WebSocket) -> None:
        async with self._lock:
            if self._session and self._session.ws is not ws:
                await self._cancel_pending("worker replaced")
            self._session = WorkerSession(ws=ws)

    async def detach(self, ws: WebSocket) -> None:
        async with self._lock:
            if self._session and self._session.ws is ws:
                self._session = None
                await self._cancel_pending("worker disconnected")

    async def handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("worker sent invalid json")
            return
        if not isinstance(msg, dict):
            return

        msg_type = msg.get("type")
        if msg_type == "register":
            await self._on_register(msg)
            return
        if msg_type == "status":
            await self._on_status(msg)
            return
        if msg_type == "pong":
            return

        req_id = msg.get("id")
        if not req_id:
            return

        if msg.get("stream") is True:
            pending = self._pending_streams.get(req_id)
            if not pending:
                return
            status = int(msg.get("status", 200))
            if status >= 400:
                pending.error = WorkerRequestError(status, msg.get("body"))
                await pending.queue.put(_STREAM_DONE)
                return
            if msg.get("done"):
                await pending.queue.put(_STREAM_DONE)
            else:
                await pending.queue.put(msg.get("chunk", ""))
            return

        fut = self._pending.get(req_id)
        if fut and not fut.done():
            fut.set_result(msg)

    async def _on_register(self, msg: dict) -> None:
        if not self._session:
            return
        self._session.hostname = str(msg.get("hostname") or "")
        self._session.model = str(msg.get("model") or "")
        self._session.version = str(msg.get("version") or "")
        self._session.mode = str(msg.get("mode") or "proxy")
        remote_ip = msg.get("remote_ip")
        self._session.remote_ip = str(remote_ip) if remote_ip else None
        logger.info(
            "worker registered hostname=%s model=%s",
            self._session.hostname,
            self._session.model,
        )

    async def _on_status(self, msg: dict) -> None:
        if not self._session:
            return
        state = msg.get("state")
        if state:
            self._session.state = str(state)

    async def _cancel_pending(self, reason: str) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(WorkerOffline(reason))
        self._pending.clear()
        for pending in self._pending_streams.values():
            pending.error = WorkerOffline(reason)
            await pending.queue.put(_STREAM_DONE)
        self._pending_streams.clear()

    async def send_ping(self) -> None:
        session = self._session
        if not session:
            return
        try:
            await session.ws.send_json({"type": "ping"})
        except Exception:
            logger.debug("worker ping failed", exc_info=True)

    async def chat_completions(
        self,
        body: dict[str, Any],
        *,
        request_id: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        session = self._session
        if not session:
            raise WorkerOffline("worker_offline")
        if session.state != "ready":
            raise WorkerBusy(f"worker_{session.state}")

        req_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
        payload = {
            "id": req_id,
            "method": "POST",
            "path": "/v1/chat/completions",
            "body": {**body, "stream": False},
        }

        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(max_retries):
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._pending[req_id] = fut
            try:
                await session.ws.send_json(payload)
                msg = await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError as exc:
                last_err = exc
                self._pending.pop(req_id, None)
                raise WorkerRequestError(504, {"error": "timeout"}) from exc
            finally:
                self._pending.pop(req_id, None)

            status = int(msg.get("status", 200))
            if status == 429 and attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
                req_id = f"{request_id or 'req'}-{attempt + 1}-{uuid.uuid4().hex[:6]}"
                payload["id"] = req_id
                continue
            if status >= 400:
                raise WorkerRequestError(status, msg.get("body"))
            return msg.get("body") or {}

        if last_err:
            raise last_err
        raise WorkerRequestError(429, {"error": "worker_busy"})

    async def chat_completions_stream(
        self,
        body: dict[str, Any],
        *,
        request_id: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> AsyncIterator[str]:
        session = self._session
        if not session:
            raise WorkerOffline("worker_offline")
        if session.state != "ready":
            raise WorkerBusy(f"worker_{session.state}")

        req_id = request_id or f"stream-{uuid.uuid4().hex[:12]}"
        payload = {
            "id": req_id,
            "method": "POST",
            "path": "/v1/chat/completions",
            "body": {**body, "stream": True},
        }

        delay = 1.0
        for attempt in range(max_retries):
            pending = _StreamPending()
            self._pending_streams[req_id] = pending
            should_retry = False
            try:
                await session.ws.send_json(payload)
                while True:
                    try:
                        item = await asyncio.wait_for(pending.queue.get(), timeout=timeout)
                    except asyncio.TimeoutError as exc:
                        raise WorkerRequestError(504, {"error": "timeout"}) from exc
                    if item is _STREAM_DONE:
                        if pending.error:
                            if pending.error.status == 429 and attempt < max_retries - 1:
                                should_retry = True
                            else:
                                raise pending.error
                        return
                    for token in parse_ollama_sse_tokens(str(item)):
                        yield token
            finally:
                self._pending_streams.pop(req_id, None)
            if should_retry:
                await asyncio.sleep(delay)
                delay *= 2
                req_id = f"{request_id or 'stream'}-{attempt + 1}-{uuid.uuid4().hex[:6]}"
                payload["id"] = req_id
                continue
            return

        raise WorkerRequestError(429, {"error": "worker_busy"})
