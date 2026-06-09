"""FIFO scan queue — worker concurrency is 1 for LLM discovery."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable
from typing import Any

from app.database import SessionLocal
from app.deid import service
from app.deid.scan_events import get_scan_event_bus
from app.deid.worker.client import get_worker_client

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Any]


class ScanQueue:
    """Serializes scan jobs that need the Mac Worker (use_worker=True)."""

    def __init__(self, session_factory: SessionFactory | None = None, app=None) -> None:
        self._waiting: deque[int] = deque()
        self._current: int | None = None
        self._lock = asyncio.Lock()
        self._app = app
        self._session_factory = session_factory or SessionLocal

    def _worker_client(self):
        if self._app is None:
            return None
        return get_worker_client(self._app)

    def status_dict(self) -> dict[str, Any]:
        return {
            "current_job_id": self._current,
            "waiting_job_ids": list(self._waiting),
            "waiting_count": len(self._waiting),
        }

    def queue_position(self, job_id: int) -> int | None:
        """Return 1-based queue position, 0 if currently running, None if not queued."""
        if self._current == job_id:
            return 0
        try:
            idx = list(self._waiting).index(job_id)
            return idx + 1
        except ValueError:
            return None

    async def submit(self, job_id: int) -> dict[str, Any]:
        """Enqueue or start scan immediately. Returns {status, queue_position}."""
        db = self._session_factory()
        try:
            from app.models_deid import DeidJob

            job = db.get(DeidJob, job_id)
            if not job:
                return {"status": "error", "queue_position": None, "message": "任务不存在"}

            needs_queue = service.job_needs_worker_queue(db, job, self._worker_client())
            bus = get_scan_event_bus()
            if not needs_queue:
                service.set_job_progress(
                    db,
                    job,
                    phase="starting",
                    percent=0,
                    message="准备解析…",
                    queue_position=0,
                )
                job.status = "scanning"
                db.commit()
                bus.emit(job_id, {"type": "log", "line": "任务已提交，开始扫描…"})
                asyncio.create_task(self._run_scan(job_id, queued=False))
                return {"status": "scanning", "queue_position": 0}

            async with self._lock:
                if self._current is None:
                    self._current = job_id
                    service.set_job_progress(
                        db,
                        job,
                        phase="starting",
                        percent=0,
                        message="准备解析…",
                        queue_position=0,
                    )
                    job.status = "scanning"
                    db.commit()
                    bus.emit(job_id, {"type": "log", "line": "任务已提交，开始扫描…"})
                    asyncio.create_task(self._run_scan(job_id, queued=True))
                    return {"status": "scanning", "queue_position": 0}

                self._waiting.append(job_id)
                pos = len(self._waiting)
                service.set_job_progress(
                    db,
                    job,
                    phase="queued",
                    percent=0,
                    message=f"排队中（第 {pos} 位）",
                    queue_position=pos,
                )
                job.status = "queued"
                db.commit()
                return {"status": "queued", "queue_position": pos}
        finally:
            db.close()

    async def _run_scan(self, job_id: int, *, queued: bool) -> None:
        db = self._session_factory()
        try:
            await service.scan_job_async(
                db,
                job_id,
                worker_router=self._worker_client(),
                queue=self if queued else None,
            )
        except Exception:
            logger.exception("scan failed for job %s", job_id)
            from app.models_deid import DeidJob

            job = db.get(DeidJob, job_id)
            if job and job.status in ("scanning", "queued"):
                msg = "扫描失败，请重试或手动添加实体"
                payload = {
                    "phase": "error",
                    "percent": 0,
                    "message": msg,
                    "fallback": "manual",
                }
                job.progress_json = json.dumps(payload, ensure_ascii=False)
                job.status = "draft"
                db.commit()
                bus = get_scan_event_bus()
                bus.emit(job_id, {"type": "error", "message": msg})
                bus.close(job_id)
        finally:
            db.close()
            if queued:
                await self._finish_and_advance(job_id)

    async def _finish_and_advance(self, finished_job_id: int) -> None:
        async with self._lock:
            if self._current == finished_job_id:
                self._current = None
            if not self._waiting:
                return
            next_id = self._waiting.popleft()
            self._current = next_id
            db = self._session_factory()
            try:
                from app.models_deid import DeidJob

                job = db.get(DeidJob, next_id)
                if job:
                    service.set_job_progress(
                        db,
                        job,
                        phase="starting",
                        percent=0,
                        message="准备解析…",
                        queue_position=0,
                    )
                    job.status = "scanning"
                    db.commit()
            finally:
                db.close()
            asyncio.create_task(self._run_scan(next_id, queued=True))
            await self._refresh_waiting_positions()

    async def _refresh_waiting_positions(self) -> None:
        db = self._session_factory()
        try:
            from app.models_deid import DeidJob

            for idx, jid in enumerate(self._waiting, start=1):
                job = db.get(DeidJob, jid)
                if job and job.status == "queued":
                    service.set_job_progress(
                        db,
                        job,
                        phase="queued",
                        percent=0,
                        message=f"排队中（第 {idx} 位）",
                        queue_position=idx,
                    )
            db.commit()
        finally:
            db.close()
