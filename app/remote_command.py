"""In-memory relay for explicit remote command execution sessions."""
from __future__ import annotations

import asyncio
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


TARGET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$")
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_SHELL = "cmd"


class RemoteCommandError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class RemoteCommandSession:
    target_id: str
    ws: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    hostname: str | None = None
    platform: str | None = None
    shell: str | None = None

    def status_dict(self) -> dict[str, Any]:
        return {
            "id": self.target_id,
            "online": True,
            "hostname": self.hostname,
            "platform": self.platform,
            "shell": self.shell,
            "connected_at": self.connected_at.isoformat(),
        }


class RemoteCommandRelay:
    """Tracks controlled machines and routes command requests to them."""

    def __init__(self) -> None:
        self._known_ids: set[str] = set()
        self._sessions: dict[str, RemoteCommandSession] = {}
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def generate_target_id(self) -> str:
        return f"rc-{secrets.token_urlsafe(6).replace('-', '').replace('_', '')}"

    def normalize_target_id(self, target_id: str | None) -> str:
        target_id = (target_id or "").strip()
        if not target_id:
            target_id = self.generate_target_id()
        if not TARGET_ID_RE.match(target_id):
            raise RemoteCommandError(
                400,
                "target_id must be 3-64 chars: letters, numbers, underscore, dash, dot",
            )
        return target_id

    async def register_target_id(self, target_id: str | None) -> str:
        target_id = self.normalize_target_id(target_id)
        async with self._lock:
            self._known_ids.add(target_id)
        return target_id

    async def attach(self, ws: WebSocket, target_id: str) -> RemoteCommandSession:
        async with self._lock:
            self._known_ids.add(target_id)
            old = self._sessions.get(target_id)
            if old and old.ws is not ws:
                await old.ws.close(code=1012, reason="target replaced")
            session = RemoteCommandSession(target_id=target_id, ws=ws)
            self._sessions[target_id] = session
            return session

    async def detach(self, ws: WebSocket) -> None:
        async with self._lock:
            disconnected_ids = [
                target_id
                for target_id, session in self._sessions.items()
                if session.ws is ws
            ]
            for target_id in disconnected_ids:
                self._sessions.pop(target_id, None)
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RemoteCommandError(503, "target_disconnected"))

    async def handle_message(self, raw: dict[str, Any]) -> None:
        msg_type = raw.get("type")
        if msg_type == "hello":
            await self._update_metadata(raw)
            return
        if msg_type == "result":
            req_id = str(raw.get("request_id") or "")
            fut = self._pending.get(req_id)
            if fut and not fut.done():
                fut.set_result(raw)

    async def _update_metadata(self, raw: dict[str, Any]) -> None:
        target_id = str(raw.get("target_id") or "")
        session = self._sessions.get(target_id)
        if not session:
            return
        session.hostname = _optional_str(raw.get("hostname"))
        session.platform = _optional_str(raw.get("platform"))
        session.shell = _optional_str(raw.get("shell"))

    def list_targets(self) -> list[dict[str, Any]]:
        targets = []
        for target_id in sorted(self._known_ids):
            targets.append(self.target_status(target_id))
        for target_id, session in self._sessions.items():
            if target_id not in self._known_ids:
                targets.append(session.status_dict())
        return targets

    def target_status(self, target_id: str) -> dict[str, Any]:
        session = self._sessions.get(target_id)
        if not session:
            return {"id": target_id, "online": False, "registered": target_id in self._known_ids}
        return session.status_dict()

    async def execute(
        self,
        *,
        target_id: str,
        command: str,
        shell: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        session = self._sessions.get(target_id)
        if not session:
            raise RemoteCommandError(404, "target_offline")
        command = command.strip()
        if not command:
            raise RemoteCommandError(400, "command_required")
        if timeout < 1 or timeout > 600:
            raise RemoteCommandError(400, "timeout must be between 1 and 600 seconds")

        request_id = f"cmd-{uuid.uuid4().hex[:12]}"
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[request_id] = fut
        try:
            await session.ws.send_json(
                {
                    "type": "exec",
                    "request_id": request_id,
                    "command": command,
                    "shell": shell or _DEFAULT_SHELL,
                    "timeout": timeout,
                }
            )
            result = await asyncio.wait_for(fut, timeout=timeout + 5)
        except asyncio.TimeoutError as exc:
            raise RemoteCommandError(504, "command_timeout") from exc
        finally:
            self._pending.pop(request_id, None)

        return {
            "request_id": request_id,
            "target_id": target_id,
            "exit_code": int(result.get("exit_code", -1)),
            "stdout": str(result.get("stdout") or ""),
            "stderr": str(result.get("stderr") or ""),
            "duration_ms": result.get("duration_ms"),
        }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
