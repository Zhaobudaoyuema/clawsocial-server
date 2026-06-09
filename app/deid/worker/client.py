"""Resolve Mac Worker client: local WebSocket router or remote dev relay."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.deid.worker.relay_client import RemoteWorkerRelay
from app.deid.worker.router import WorkerRouter


def get_worker_client(app: FastAPI) -> WorkerRouter | RemoteWorkerRelay | None:
    relay: RemoteWorkerRelay | None = getattr(app.state, "worker_relay", None)
    if relay and relay.enabled:
        return relay
    return getattr(app.state, "worker_router", None)


def worker_client_online(client: Any) -> bool:
    session = getattr(client, "session", None)
    return bool(session and getattr(session, "state", "offline") == "ready")
