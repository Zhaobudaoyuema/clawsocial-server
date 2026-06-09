"""REST + SSE API for deid local chat."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deid.chat.service import stream_chat_reply
from app.deid.chat.session import ChatSessionStore, list_chat_jobs

router = APIRouter(prefix="/api/deid/chat", tags=["deid-chat"])


class ChatMessageIn(BaseModel):
    content: str = Field(..., min_length=1)


def _get_store(request: Request) -> ChatSessionStore:
    store = getattr(request.app.state, "chat_session_store", None)
    if not store:
        store = ChatSessionStore()
        request.app.state.chat_session_store = store
    return store


@router.get("/jobs")
def chat_jobs(db: Session = Depends(get_db)):
    return list_chat_jobs(db)


@router.post("/sessions")
async def create_session(
    request: Request,
    mode: str = Form("none"),
    job_id: int | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    store = _get_store(request)
    session = await store.create(db, mode=mode, job_id=job_id, file=file)
    return {
        "session_id": session.id,
        "doc_label": session.doc_label,
        "has_doc": session.doc_text is not None,
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request):
    store = _get_store(request)
    session = store.get(session_id)
    if not session:
        from fastapi import HTTPException

        raise HTTPException(404, "会话不存在或已过期")
    return store.session_meta(session)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request):
    store = _get_store(request)
    if not store.delete(session_id):
        from fastapi import HTTPException

        raise HTTPException(404, "会话不存在")
    return {"ok": True}


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    body: ChatMessageIn,
    request: Request,
):
    store = _get_store(request)
    worker_router = getattr(request.app.state, "worker_router", None)

    async def gen():
        async for line in stream_chat_reply(store, worker_router, session_id, body.content):
            yield line

    return StreamingResponse(gen(), media_type="text/event-stream")
