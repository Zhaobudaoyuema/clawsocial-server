"""Public v11 compatibility, with grants isolated from the authenticated v12 relay."""
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field

from app.api.remote_command import ExecuteCommandIn, serve_target
from app.remote_command import RemoteCommandError

# The parent lifespan owns initialization; this application's state is the sole
# owner of legacy grants. No legacy handler ever resolves the v12 relay.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class RegisterTargetIn(BaseModel):
    target_id: str | None = Field(default=None, min_length=3, max_length=64)
    expires_in_minutes: Literal[10, 30, 180] = 10


@app.post("/api/remote-command/targets/register")
async def register_target(request: Request, payload: RegisterTargetIn):
    relay = request.app.state.remote_command_relay
    try:
        grant = await relay.register_target_id(payload.target_id, expires_in_minutes=payload.expires_in_minutes)
    except RemoteCommandError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    return {
        "id": grant.target_id,
        "expires_at": grant.expires_at.isoformat(),
        "expires_in_minutes": payload.expires_in_minutes,
        "websocket_path": f"/ws/remote-command/target?id={grant.target_id}",
    }


@app.get("/api/remote-command/targets")
async def list_targets(request: Request):
    return {"targets": request.app.state.remote_command_relay.list_targets()}


@app.get("/api/remote-command/targets/{target_id}")
async def target_status(request: Request, target_id: str):
    return request.app.state.remote_command_relay.target_status(target_id)


@app.post("/api/remote-command/execute")
async def execute_command(request: Request, payload: ExecuteCommandIn):
    try:
        return await request.app.state.remote_command_relay.execute(
            target_id=payload.target_id, command=payload.command,
            shell=payload.shell, timeout=payload.timeout,
        )
    except RemoteCommandError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


@app.websocket("/ws/remote-command/target")
async def ws_remote_target(ws: WebSocket, id: str = Query(default="")):
    relay = ws.app.state.remote_command_relay
    try:
        target_id = relay.normalize_target_id(id)
        session = await relay.attach(ws, target_id)
    except RemoteCommandError as exc:
        await ws.close(code=1008, reason=exc.detail)
        return
    await serve_target(ws, target_id, session, relay)
