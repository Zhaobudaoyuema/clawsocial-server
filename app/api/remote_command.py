"""Remote command relay API."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.database import get_db
from app.remote_command_security import require_operator, create_invite, consume_invite
from pydantic import BaseModel, Field

from app.remote_command import RemoteCommandError

router = APIRouter(prefix="/api/remote-command", tags=["remote-command"])
ws_router = APIRouter(tags=["remote-command"])


class RegisterTargetIn(BaseModel):
    invite_token: str = Field(..., min_length=40, max_length=128)


class InviteIn(BaseModel):
    session_minutes: Literal[10, 30, 180] = 30
    lifetime_minutes: int = Field(default=30, ge=1, le=180)


@router.post("/invites")
def issue_invite(payload: InviteIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_operator(authorization)
    return create_invite(db, payload.session_minutes, payload.lifetime_minutes)


class ExecuteCommandIn(BaseModel):
    target_id: str = Field(..., min_length=3, max_length=64)
    command: str = Field(..., min_length=1, max_length=20000)
    shell: Literal["bash", "sh", "cmd", "powershell", "pwsh"] | None = None
    timeout: float = Field(default=60.0, ge=1.0, le=600.0)


@router.post("/targets/register")
async def register_target(request: Request, payload: RegisterTargetIn, db: Session = Depends(get_db)):
    relay = _relay_from_request(request)
    minutes = consume_invite(db, payload.invite_token)
    grant = await relay.register_target_id(None, expires_in_minutes=minutes)
    connection_token = relay.issue_connection_token(grant.target_id)
    return {
        "id": grant.target_id,
        "connection_token": connection_token,
        "expires_at": grant.expires_at.isoformat(),
        "expires_in_minutes": minutes,
        "websocket_path": f"/ws/remote-command/target?id={grant.target_id}",
    }


@router.get("/targets")
async def list_targets(request: Request, authorization: str | None = Header(default=None)):
    require_operator(authorization)
    relay = _relay_from_request(request)
    return {"targets": relay.list_targets()}


@router.get("/targets/{target_id}")
async def target_status(request: Request, target_id: str, authorization: str | None = Header(default=None)):
    require_operator(authorization)
    relay = _relay_from_request(request)
    return relay.target_status(target_id)


@router.post("/execute")
async def execute_command(
    request: Request,
    payload: ExecuteCommandIn,
    authorization: str | None = Header(default=None),
):
    require_operator(authorization)
    relay = _relay_from_request(request)
    try:
        return await relay.execute(
            target_id=payload.target_id,
            command=payload.command,
            shell=payload.shell,
            timeout=payload.timeout,
        )
    except RemoteCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@ws_router.websocket("/ws/remote-command/target")
async def ws_remote_target(ws: WebSocket, id: str = Query(default="")):
    relay = ws.app.state.remote_command_relay
    try:
        target_id = relay.normalize_target_id(id)
        relay.verify_connection_token(target_id, ws.headers.get("authorization"))
        session = await relay.attach(ws, target_id)
    except RemoteCommandError as exc:
        await ws.close(code=1008, reason=exc.detail)
        return

    await serve_target(ws, target_id, session, relay)


async def serve_target(ws, target_id, session, relay):
    """Serve one attached target; caller chooses and authenticates its relay."""
    await ws.accept()
    await ws.send_json(
        {
            "type": "registered",
            "result_chunks": 1,
            "id": target_id,
            "expires_at": session.expires_at.isoformat(),
        }
    )
    try:
        while True:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=max(0.01, (session.expires_at - datetime.now(timezone.utc)).total_seconds()))
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                if len(raw.encode("utf-8")) > 262144:
                    await ws.close(code=1009, reason="message too large")
                    break
                continue
            # Legacy agents send a single result; permit it up to the transport
            # limit. New agents keep all chunk frames below the original limit.
            if len(raw.encode("utf-8")) > 262144 and not (
                isinstance(msg, dict) and msg.get("type") == "result"
            ):
                await ws.close(code=1009, reason="message too large")
                break
            if isinstance(msg, dict):
                msg["target_id"] = target_id
                await relay.handle_message(msg)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        await relay.detach(ws)
        if datetime.now(timezone.utc) >= session.expires_at:
            await ws.close(code=1000, reason="authorization expired")


def _relay_from_request(request: Request):
    relay = getattr(request.app.state, "remote_command_relay", None)
    if relay is None:
        raise HTTPException(status_code=503, detail="remote_command_relay_not_ready")
    return relay
