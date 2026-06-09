"""Mac Worker session state."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import WebSocket


@dataclass
class WorkerSession:
    ws: WebSocket
    hostname: str = ""
    model: str = ""
    version: str = ""
    mode: str = "proxy"
    remote_ip: str | None = None
    state: str = "ready"
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_status_dict(self) -> dict:
        return {
            "online": True,
            "state": self.state,
            "model": self.model,
            "hostname": self.hostname,
            "version": self.version,
            "mode": self.mode,
        }
