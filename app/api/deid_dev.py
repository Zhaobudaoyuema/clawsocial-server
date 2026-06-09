"""Dev-only HTTP relay: local Windows → production server → Mac Worker."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deid.worker.errors import WorkerBusy, WorkerOffline, WorkerRequestError
from app.deid.worker.relay_auth import relay_enabled, verify_relay_auth

router = APIRouter(prefix="/api/deid/dev", tags=["deid-dev"])


class ChatCompletionsRelayIn(BaseModel):
    body: dict[str, Any]
    request_id: str | None = None
    timeout: float = Field(default=120.0, ge=1.0, le=600.0)
    stream: bool = False


@router.get("/worker/status")
def dev_worker_status(request: Request):
    verify_relay_auth(request)
    worker_router = getattr(request.app.state, "worker_router", None)
    if not worker_router:
        raise HTTPException(status_code=503, detail="worker_router_not_ready")
    return worker_router.status_dict()


@router.post("/worker/chat-completions")
async def dev_worker_chat_completions(request: Request, payload: ChatCompletionsRelayIn):
    verify_relay_auth(request)
    worker_router = getattr(request.app.state, "worker_router", None)
    if not worker_router:
        raise HTTPException(status_code=503, detail="worker_router_not_ready")
    if not worker_router.session:
        raise HTTPException(status_code=503, detail="worker_offline")
    if worker_router.session.state != "ready":
        raise HTTPException(status_code=503, detail=f"worker_{worker_router.session.state}")

    body = payload.body
    if payload.stream or body.get("stream"):
        async def event_stream():
            try:
                async for token in worker_router.chat_completions_stream(
                    body,
                    request_id=payload.request_id,
                    timeout=payload.timeout,
                ):
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except WorkerOffline as exc:
                yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            except WorkerBusy as exc:
                yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            except WorkerRequestError as exc:
                yield f"data: {json.dumps({'error': f'status_{exc.status}'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        result = await worker_router.chat_completions(
            body,
            request_id=payload.request_id,
            timeout=payload.timeout,
        )
    except WorkerOffline as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WorkerBusy as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except WorkerRequestError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.body) from exc

    return {"body": result}


def include_dev_relay_routes(app) -> None:
    if relay_enabled():
        app.include_router(router)
