"""In-memory relay for explicit remote command execution sessions."""
from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import WebSocket


TARGET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$")
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_SHELL = "cmd"
_DEFAULT_EXPIRES_IN_MINUTES = 10
_ALLOWED_EXPIRES_IN_MINUTES = {10, 30, 180}


class RemoteCommandError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class RemoteCommandGrant:
    target_id: str
    expires_at: datetime
    connection_token_hash: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    last_seen_at: datetime | None = None
    hostname: str | None = None
    platform: str | None = None
    shell: str | None = None

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def status_dict(self) -> dict[str, Any]:
        expired = self.expired
        return {
            "id": self.target_id,
            "online": False,
            "state": "expired" if expired else "offline_authorized",
            "registered": True,
            "expired": expired,
            "hostname": self.hostname,
            "platform": self.platform,
            "shell": self.shell,
            "created_at": self.created_at.isoformat(),
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "disconnected_at": self.disconnected_at.isoformat() if self.disconnected_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass
class RemoteCommandSession:
    target_id: str
    ws: WebSocket
    expires_at: datetime
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    hostname: str | None = None
    platform: str | None = None
    shell: str | None = None

    def status_dict(self) -> dict[str, Any]:
        return {
            "id": self.target_id,
            "online": True,
            "state": "online",
            "registered": True,
            "hostname": self.hostname,
            "platform": self.platform,
            "shell": self.shell,
            "connected_at": self.connected_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "expired": datetime.now(timezone.utc) >= self.expires_at,
        }


class RemoteCommandRelay:
    """Tracks controlled machines and routes command requests to them."""

    def __init__(self) -> None:
        self._grants: dict[str, RemoteCommandGrant] = {}
        self._sessions: dict[str, RemoteCommandSession] = {}
        self._pending: dict[str, tuple[str, asyncio.Future]] = {}
        self._lock = asyncio.Lock()

    def issue_connection_token(self, target_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self._active_grant(target_id).connection_token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token

    def verify_connection_token(self, target_id: str, authorization: str | None) -> None:
        grant = self._active_grant(target_id)
        scheme, _, token = (authorization or "").partition(" ")
        hashed = hashlib.sha256(token.encode()).hexdigest()
        if scheme.lower() != "bearer" or not grant.connection_token_hash or not secrets.compare_digest(hashed, grant.connection_token_hash):
            raise RemoteCommandError(403, "target_connection_token_required")

    def generate_target_id(self) -> str:
        return f"rc-{secrets.token_urlsafe(16).replace('-', '').replace('_', '')}"

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

    async def register_target_id(
        self,
        target_id: str | None,
        *,
        expires_in_minutes: int = _DEFAULT_EXPIRES_IN_MINUTES,
    ) -> RemoteCommandGrant:
        target_id = self.normalize_target_id(target_id)
        if expires_in_minutes not in _ALLOWED_EXPIRES_IN_MINUTES:
            raise RemoteCommandError(400, "expires_in_minutes must be 10, 30, or 180")
        now = datetime.now(timezone.utc)
        grant = RemoteCommandGrant(
            target_id=target_id,
            created_at=now,
            expires_at=now + timedelta(minutes=expires_in_minutes),
        )
        async with self._lock:
            self._grants[target_id] = grant
        return grant

    async def attach(self, ws: WebSocket, target_id: str) -> RemoteCommandSession:
        async with self._lock:
            grant = self._active_grant(target_id)
            old = self._sessions.get(target_id)
            if old and old.ws is not ws:
                raise RemoteCommandError(409, "target_already_connected")
            session = RemoteCommandSession(
                target_id=target_id,
                ws=ws,
                expires_at=grant.expires_at,
            )
            self._sessions[target_id] = session
            grant.connected_at = session.connected_at
            grant.disconnected_at = None
            grant.last_seen_at = session.connected_at
            return session

    async def detach(self, ws: WebSocket) -> None:
        async with self._lock:
            disconnected_ids = [
                target_id
                for target_id, session in self._sessions.items()
                if session.ws is ws
            ]
            now = datetime.now(timezone.utc)
            for target_id in disconnected_ids:
                grant = self._grants.get(target_id)
                if grant:
                    grant.disconnected_at = now
                    grant.last_seen_at = now
                self._sessions.pop(target_id, None)
            for owner, fut in self._pending.values():
                if owner in disconnected_ids and not fut.done():
                    fut.set_exception(RemoteCommandError(503, "target_disconnected"))

    async def clear_all(self, *, reason: str = "remote_command_reset") -> dict[str, int]:
        """Drop all grants, sessions, and pending command requests."""
        async with self._lock:
            sessions = list(self._sessions.values())
            pending = [fut for _, fut in self._pending.values()]
            grant_count = len(self._grants)
            session_count = len(sessions)
            pending_count = len(pending)
            self._grants.clear()
            self._sessions.clear()
            self._pending.clear()

        for fut in pending:
            if not fut.done():
                fut.set_exception(RemoteCommandError(503, reason))
        for session in sessions:
            try:
                await session.ws.close(code=1012, reason=reason)
            except Exception:
                pass
        return {
            "grants": grant_count,
            "sessions": session_count,
            "pending": pending_count,
        }

    async def handle_message(self, raw: dict[str, Any]) -> None:
        msg_type = raw.get("type")
        if msg_type == "hello":
            await self._update_metadata(raw)
            return
        if msg_type == "result":
            req_id = str(raw.get("request_id") or "")
            pending = self._pending.get(req_id)
            if pending:
                owner, fut = pending
                if owner == raw.get("target_id") and not fut.done():
                    fut.set_result(raw)

    async def _update_metadata(self, raw: dict[str, Any]) -> None:
        target_id = str(raw.get("target_id") or "")
        session = self._sessions.get(target_id)
        if not session:
            return
        session.hostname = _optional_str(raw.get("hostname"))
        session.platform = _optional_str(raw.get("platform"))
        session.shell = _optional_str(raw.get("shell"))
        grant = self._grants.get(target_id)
        if grant:
            grant.hostname = session.hostname
            grant.platform = session.platform
            grant.shell = session.shell
            grant.last_seen_at = datetime.now(timezone.utc)

    def list_targets(self) -> list[dict[str, Any]]:
        targets = []
        for target_id in sorted(self._grants):
            targets.append(self.target_status(target_id))
        for target_id, session in self._sessions.items():
            if target_id not in self._grants:
                targets.append(session.status_dict())
        return targets

    def target_status(self, target_id: str) -> dict[str, Any]:
        session = self._sessions.get(target_id)
        if session and datetime.now(timezone.utc) < session.expires_at:
            return session.status_dict()
        grant = self._grants.get(target_id)
        if grant:
            return grant.status_dict()
        return {
            "id": target_id,
            "online": False,
            "state": "unregistered",
            "registered": False,
            "expired": False,
        }

    def _active_grant(self, target_id: str) -> RemoteCommandGrant:
        grant = self._grants.get(target_id)
        if not grant:
            raise RemoteCommandError(404, "target_not_registered")
        if grant.expired:
            self._sessions.pop(target_id, None)
            raise RemoteCommandError(410, "target_expired")
        return grant

    async def execute(
        self,
        *,
        target_id: str,
        command: str,
        shell: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        self._active_grant(target_id)
        session = self._sessions.get(target_id)
        if not session:
            raise RemoteCommandError(409, "target_offline")
        if datetime.now(timezone.utc) >= session.expires_at:
            self._sessions.pop(target_id, None)
            try:
                await session.ws.close(code=1008, reason="target expired")
            finally:
                raise RemoteCommandError(410, "target_expired")
        command = command.strip()
        if not command:
            raise RemoteCommandError(400, "command_required")
        if timeout < 1 or timeout > 600:
            raise RemoteCommandError(400, "timeout must be between 1 and 600 seconds")

        request_id = f"cmd-{uuid.uuid4().hex[:12]}"
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        if len(self._pending) >= 32 or any(owner == target_id for owner, _ in self._pending.values()):
            raise RemoteCommandError(429, "target_busy_or_server_limit")
        self._pending[request_id] = (target_id, fut)
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
