"""Generic Mac Worker flow executor for deid pipelines."""
from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.deid.worker.errors import WorkerBusy, WorkerOffline, WorkerRequestError

try:
    from sqlalchemy.orm import Session
except ImportError:  # pragma: no cover
    Session = object  # type: ignore[misc, assignment]

DEFAULT_WORKER_MAX_TOKENS = 8192


def worker_max_tokens() -> int:
    return int(os.getenv("DEID_LLM_MAX_TOKENS", str(DEFAULT_WORKER_MAX_TOKENS)))


def worker_max_tokens_detect() -> int:
    return int(os.getenv("DEID_DEEP_MAX_TOKENS_DETECT", "256"))


def worker_max_tokens_suggest() -> int:
    return int(os.getenv("DEID_DEEP_MAX_TOKENS_SUGGEST", "128"))


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 2)


@dataclass
class FlowItem:
    """One unit of work passed to the Worker (chunk, window, or single prompt)."""

    text: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowResult:
    """Aggregated result from a Worker flow run."""

    items: list[Any] = field(default_factory=list)
    chunks: int = 0
    skipped: str | None = None
    worker_model: str | None = None
    errors: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_ms: int = 0
    raw_by_chunk: list[str] = field(default_factory=list)


async def run_worker_flow(
    flow_id: str,
    units: list[FlowItem],
    router,
    *,
    job_id: int | None = None,
    db: Session | None = None,
    system_prompt: str,
    build_user_message: Callable[[FlowItem, int, int], str],
    parse_chunk: Callable[[str, FlowItem], list[Any]],
    enabled: bool = True,
    max_tokens: int | None = None,
    timeout: float | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> FlowResult:
    """
    Run a Worker flow over multiple input units (chunks/windows).

    parse_chunk receives raw LLM content and the FlowItem for context validation.
    """
    result = FlowResult()
    started = time.monotonic()

    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    if not enabled:
        result.skipped = "llm_disabled"
        return result
    if not router or not router.session:
        result.skipped = "worker_offline"
        return result
    if router.session.state != "ready":
        result.skipped = f"worker_{router.session.state}"
        return result

    if not units:
        result.chunks = 0
        return result

    timeout_sec = timeout if timeout is not None else float(os.getenv("DEID_LLM_TIMEOUT_SEC", "180"))
    tokens = max_tokens if max_tokens is not None else worker_max_tokens()
    model = os.getenv("DEID_LLM_MODEL") or router.session.model
    result.worker_model = model
    result.chunks = len(units)
    prompt = (system_prompt or "").strip()
    jid = job_id if job_id is not None else 0

    for idx, unit in enumerate(units):
        if on_progress:
            on_progress(idx + 1, len(units))
        emit({"type": "flow_chunk_start", "flow_id": flow_id, "index": idx + 1, "total": len(units)})

        user_content = build_user_message(unit, idx + 1, len(units))
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            "reasoning_effort": "none",
            "temperature": 0,
            "max_tokens": tokens,
        }
        req_id = f"{flow_id}-{jid}-{idx}-{uuid.uuid4().hex[:8]}"
        chunk_prompt_est = _estimate_tokens(prompt) + _estimate_tokens(user_content)
        chunk_started = time.monotonic()
        content = ""
        parsed: list[Any] = []
        call_error: str | None = None
        usage_prompt = chunk_prompt_est
        usage_completion = 0

        try:
            resp = await router.chat_completions(body, request_id=req_id, timeout=timeout_sec)
            choices = resp.get("choices") or []
            if choices:
                content = (choices[0].get("message") or {}).get("content") or ""
            usage = resp.get("usage") or {}
            usage_prompt = int(usage.get("prompt_tokens") or chunk_prompt_est)
            usage_completion = int(usage.get("completion_tokens") or _estimate_tokens(content))
            result.prompt_tokens += usage_prompt
            result.completion_tokens += usage_completion
            result.raw_by_chunk.append(content)
            if content:
                emit({"type": "token", "content": content})
            parsed = parse_chunk(content, unit)
            result.items.extend(parsed)
            emit(
                {
                    "type": "log",
                    "line": f"[{flow_id}] 第 {idx + 1}/{len(units)} 段，解析 {len(parsed)} 条",
                }
            )
        except WorkerOffline:
            result.skipped = "worker_offline"
            call_error = "worker_offline"
            _maybe_record_worker_call(
                db,
                job_id=jid,
                flow_id=flow_id,
                request_id=req_id,
                chunk_index=idx + 1,
                chunk_total=len(units),
                model=model,
                system_prompt=prompt,
                user_message=user_content,
                response=None,
                error=call_error,
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                parsed_count=0,
                elapsed_ms=int((time.monotonic() - chunk_started) * 1000),
            )
            break
        except WorkerBusy as exc:
            result.skipped = str(exc)
            call_error = str(exc)
            _maybe_record_worker_call(
                db,
                job_id=jid,
                flow_id=flow_id,
                request_id=req_id,
                chunk_index=idx + 1,
                chunk_total=len(units),
                model=model,
                system_prompt=prompt,
                user_message=user_content,
                response=None,
                error=call_error,
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                parsed_count=0,
                elapsed_ms=int((time.monotonic() - chunk_started) * 1000),
            )
            break
        except WorkerRequestError as exc:
            call_error = f"HTTP {exc.status}"
            result.errors.append(f"chunk {idx}: status {exc.status}")
            emit({"type": "log", "line": f"[{flow_id}] 第 {idx + 1} 段请求失败 (HTTP {exc.status})"})
        except Exception as exc:
            call_error = type(exc).__name__
            result.errors.append(f"chunk {idx}: {type(exc).__name__}")
            emit({"type": "log", "line": f"[{flow_id}] 第 {idx + 1} 段异常: {type(exc).__name__}"})
        else:
            _maybe_record_worker_call(
                db,
                job_id=jid,
                flow_id=flow_id,
                request_id=req_id,
                chunk_index=idx + 1,
                chunk_total=len(units),
                model=model,
                system_prompt=prompt,
                user_message=user_content,
                response=content,
                error=None,
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                parsed_count=len(parsed),
                elapsed_ms=int((time.monotonic() - chunk_started) * 1000),
            )
            continue

        _maybe_record_worker_call(
            db,
            job_id=jid,
            flow_id=flow_id,
            request_id=req_id,
            chunk_index=idx + 1,
            chunk_total=len(units),
            model=model,
            system_prompt=prompt,
            user_message=user_content,
            response=content or None,
            error=call_error,
            prompt_tokens=usage_prompt,
            completion_tokens=usage_completion,
            parsed_count=len(parsed),
            elapsed_ms=int((time.monotonic() - chunk_started) * 1000),
        )

    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    emit(
        {
            "type": "metrics",
            "flow_id": flow_id,
            "elapsed_ms": result.elapsed_ms,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "model": model,
        }
    )
    return result


def flow_items_from_text_chunks(chunks: list[str]) -> list[FlowItem]:
    return [FlowItem(text=c) for c in chunks]


def default_chunk_user_message(unit: FlowItem, index: int, total: int) -> str:
    head = f"【片段 {index}/{total}，约 {len(unit.text)} 字】"
    return f"{head}\n{unit.text}"


def _maybe_record_worker_call(db: Session | None, *, job_id: int, **kwargs) -> None:
    if db is None or not job_id:
        return
    try:
        from app.deid.worker_call_store import record_worker_call

        record_worker_call(db, job_id=job_id, **kwargs)
    except Exception:
        pass
