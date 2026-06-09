"""Streaming chat via Mac Worker."""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.deid.chat.session import ChatSessionStore
from app.deid.worker.errors import WorkerBusy, WorkerOffline, WorkerRequestError
from app.deid.worker.router import WorkerRouter


async def stream_chat_reply(
    store: ChatSessionStore,
    router: WorkerRouter | None,
    session_id: str,
    content: str,
) -> AsyncIterator[str]:
    """Yield SSE lines (data: {...}\\n\\n)."""
    session = store.get(session_id)
    if not session:
        yield _sse({"type": "error", "message": "session_not_found"})
        return

    text = (content or "").strip()
    if not text:
        yield _sse({"type": "error", "message": "empty_message"})
        return

    if not router or not router.session:
        yield _sse({"type": "error", "message": "worker_offline"})
        return
    if router.session.state != "ready":
        yield _sse({"type": "error", "message": f"worker_{router.session.state}"})
        return

    messages = store.build_messages(session, text)
    model = os.getenv("DEID_LLM_MODEL") or router.session.model
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "reasoning_effort": "none",
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    parts: list[str] = []
    req_id = f"chat-{session_id[:8]}-{len(session.messages)}"
    try:
        async for token in router.chat_completions_stream(
            body, request_id=req_id, timeout=float(os.getenv("DEID_LLM_TIMEOUT_SEC", "120"))
        ):
            parts.append(token)
            yield _sse({"type": "token", "content": token})
    except WorkerOffline:
        yield _sse({"type": "error", "message": "worker_offline"})
        return
    except WorkerBusy as exc:
        yield _sse({"type": "error", "message": str(exc)})
        return
    except WorkerRequestError as exc:
        yield _sse({"type": "error", "message": f"worker_error_{exc.status}"})
        return

    assistant = "".join(parts)
    store.append_exchange(session, text, assistant)
    yield _sse({"type": "done"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
