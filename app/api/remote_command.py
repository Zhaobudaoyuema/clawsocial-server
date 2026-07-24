"""Remote command relay API."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.remote_command import RemoteCommandError

router = APIRouter(prefix="/api/remote-command", tags=["remote-command"])
ws_router = APIRouter(tags=["remote-command"])


class RegisterTargetIn(BaseModel):
    target_id: str | None = Field(default=None, min_length=3, max_length=64)
    expires_in_minutes: Literal[10, 30, 180] = 10


class ExecuteCommandIn(BaseModel):
    target_id: str = Field(..., min_length=3, max_length=64)
    command: str = Field(..., min_length=1, max_length=20000)
    shell: Literal["bash", "sh", "cmd", "powershell", "pwsh"] | None = None
    timeout: float = Field(default=60.0, ge=1.0, le=600.0)


@router.post("/targets/register")
async def register_target(request: Request, payload: RegisterTargetIn):
    relay = _relay_from_request(request)
    try:
        grant = await relay.register_target_id(
            payload.target_id,
            expires_in_minutes=payload.expires_in_minutes,
        )
    except RemoteCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {
        "id": grant.target_id,
        "expires_at": grant.expires_at.isoformat(),
        "expires_in_minutes": payload.expires_in_minutes,
        "websocket_path": f"/ws/remote-command/target?id={grant.target_id}",
    }


@router.get("/targets")
async def list_targets(request: Request):
    relay = _relay_from_request(request)
    return {"targets": relay.list_targets()}


@router.get("/targets/{target_id}")
async def target_status(request: Request, target_id: str):
    relay = _relay_from_request(request)
    return relay.target_status(target_id)


@router.post("/execute")
async def execute_command(request: Request, payload: ExecuteCommandIn):
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
        session = await relay.attach(ws, target_id)
    except RemoteCommandError as exc:
        await ws.close(code=1008, reason=exc.detail)
        return

    await ws.accept()
    await ws.send_json(
        {
            "type": "registered",
            "id": target_id,
            "expires_at": session.expires_at.isoformat(),
        }
    )
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                msg.setdefault("target_id", target_id)
                await relay.handle_message(msg)
    except WebSocketDisconnect:
        pass
    finally:
        await relay.detach(ws)


def _relay_from_request(request: Request):
    relay = getattr(request.app.state, "remote_command_relay", None)
    if relay is None:
        raise HTTPException(status_code=503, detail="remote_command_relay_not_ready")
    return relay
