"""Persist Mac Worker LLM request/response audit log per deid job."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models_deid import DeidWorkerCall
from app.time_utils import coerce_beijing

_MAX_TEXT = 200_000


def _clip(text: str) -> str:
    if len(text) <= _MAX_TEXT:
        return text
    return text[:_MAX_TEXT] + f"\n…(截断，原长 {len(text)} 字)"


def record_worker_call(
    db: Session,
    *,
    job_id: int,
    flow_id: str,
    request_id: str,
    chunk_index: int,
    chunk_total: int,
    model: str | None,
    system_prompt: str,
    user_message: str,
    response: str | None = None,
    error: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    parsed_count: int = 0,
    elapsed_ms: int = 0,
) -> int:
    row = DeidWorkerCall(
        job_id=job_id,
        flow_id=flow_id,
        request_id=request_id,
        chunk_index=chunk_index,
        chunk_total=chunk_total,
        model=model,
        system_prompt=_clip(system_prompt or ""),
        user_message=_clip(user_message or ""),
        response_content=_clip(response or "") if response else None,
        error=error,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        parsed_count=parsed_count,
        elapsed_ms=elapsed_ms,
    )
    db.add(row)
    db.commit()
    return row.id


def list_worker_calls(db: Session, job_id: int, *, limit: int = 200) -> list[dict]:
    rows = (
        db.query(DeidWorkerCall)
        .filter(DeidWorkerCall.job_id == job_id)
        .order_by(DeidWorkerCall.id.asc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [_call_to_dict(r) for r in rows]


def delete_worker_calls_for_job(db: Session, job_id: int) -> None:
    db.query(DeidWorkerCall).filter(DeidWorkerCall.job_id == job_id).delete(
        synchronize_session=False
    )


def _call_to_dict(row: DeidWorkerCall) -> dict:
    created = coerce_beijing(row.created_at)
    return {
        "id": row.id,
        "job_id": row.job_id,
        "flow_id": row.flow_id,
        "request_id": row.request_id,
        "chunk_index": row.chunk_index,
        "chunk_total": row.chunk_total,
        "model": row.model,
        "system_prompt": row.system_prompt,
        "user_message": row.user_message,
        "response": row.response_content,
        "error": row.error,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "parsed_count": row.parsed_count,
        "elapsed_ms": row.elapsed_ms,
        "created_at": created.isoformat() if created else None,
    }
