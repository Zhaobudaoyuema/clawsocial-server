"""Generate one-sentence de-identification summary via Mac Worker."""
from __future__ import annotations

import json
from typing import Any

from app.deid.worker.errors import WorkerOffline, WorkerRequestError
from app.deid.worker.router import WorkerRouter

_SUMMARY_PROMPT = """你是财务文档脱敏助手。根据以下结构化结果，用一句中文（不超过80字）总结本次脱敏做了什么。
只输出一句话，不要列表、不要 markdown。"""


async def generate_ai_summary(
    *,
    worker_router: WorkerRouter | None,
    entity_count: int,
    replacement_count: int,
    verification_passed: bool,
    entity_type_counts: dict[str, int],
    engine: str | None,
) -> str:
    if not worker_router or not worker_router.session:
        raise WorkerOffline("worker offline")

    user_payload = {
        "entity_count": entity_count,
        "replacement_count": replacement_count,
        "verification_passed": verification_passed,
        "entity_type_counts": entity_type_counts,
        "engine": engine or "standard",
    }
    body = {
        "model": worker_router.session.model,
        "messages": [
            {"role": "system", "content": _SUMMARY_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "stream": False,
        "temperature": 0,
        "max_tokens": 128,
    }
    try:
        resp = await worker_router.chat_completions(body, request_id="ai-summary", timeout=60.0)
    except WorkerOffline:
        raise
    except WorkerRequestError as exc:
        raise RuntimeError(f"worker error {exc.status}") from exc

    choices = resp.get("choices") or []
    content = (choices[0].get("message") or {}).get("content") if choices else ""
    text = (content or "").strip().split("\n")[0][:80]
    if not text:
        raise RuntimeError("empty summary")
    return text
