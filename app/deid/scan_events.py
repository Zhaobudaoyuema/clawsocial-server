"""In-process event bus for live deid scan progress (SSE subscribers)."""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

_TTL_SEC = 600
_MAX_HISTORY = 200


class ScanEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue[dict | None]]] = {}
        self._history: dict[int, list[dict]] = {}
        self._closed_at: dict[int, float] = {}

    def emit(self, job_id: int, event: dict[str, Any]) -> None:
        history = self._history.setdefault(job_id, [])
        history.append(event)
        if len(history) > _MAX_HISTORY:
            del history[: len(history) - _MAX_HISTORY]
        for q in self._subscribers.get(job_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def history(self, job_id: int) -> list[dict]:
        return list(self._history.get(job_id, []))

    async def subscribe(self, job_id: int) -> AsyncIterator[dict]:
        q: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(job_id, []).append(q)
        try:
            for ev in self.history(job_id):
                yield ev
            while True:
                item = await q.get()
                if item is None:
                    break
                yield item
        finally:
            subs = self._subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)

    def close(self, job_id: int) -> None:
        self._closed_at[job_id] = time.monotonic()
        for q in self._subscribers.get(job_id, []):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def cleanup_expired(self) -> None:
        now = time.monotonic()
        expired = [jid for jid, ts in self._closed_at.items() if now - ts > _TTL_SEC]
        for jid in expired:
            self._closed_at.pop(jid, None)
            self._subscribers.pop(jid, None)
            self._history.pop(jid, None)


_bus = ScanEventBus()


def get_scan_event_bus() -> ScanEventBus:
    return _bus
