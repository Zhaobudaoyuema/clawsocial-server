"""LLM-based entity discovery via Mac Worker / Ollama."""
from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.deid.discovery.flows import worker_max_tokens
from app.deid.discovery.llm_parse import is_invalid_entity_name, parse_llm_entities
from app.deid.discovery.rules import DiscoveredEntity
from app.deid.engine.plan import normalize_for_match
from app.deid.prompts import build_default_scan_prompt, build_scan_user_message
from app.deid.worker.errors import WorkerBusy, WorkerOffline, WorkerRequestError


def get_llm_chunk_params() -> tuple[int, int]:
    """Shared chunk size/overlap for stats preview and LLM discovery."""
    chunk_size = int(os.getenv("DEID_LLM_CHUNK_SIZE", "4000"))
    overlap = int(os.getenv("DEID_LLM_CHUNK_OVERLAP", "300"))
    return chunk_size, overlap


def count_llm_chunks(text: str) -> int:
    chunk_size, overlap = get_llm_chunk_params()
    return len(_chunk_text(text, chunk_size, overlap))


def build_llm_chunks(text: str) -> list[str]:
    """Public helper: same chunking used by entity scan and semantic scan."""
    chunk_size, overlap = get_llm_chunk_params()
    return _chunk_text(text, chunk_size, overlap)


def split_paragraph_blocks(text: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n+", text) if b.strip()]


def chunk_paragraph_ranges(text: str) -> list[tuple[int, int]]:
    """Paragraph index ranges for each scan chunk (paragraph mode only)."""
    blocks = split_paragraph_blocks(text)
    if not blocks:
        return [(0, 1)]
    chunk_size, overlap = get_llm_chunk_params()
    return _paragraph_chunk_ranges(blocks, chunk_size, overlap)


def chunks_from_paragraph_ranges(text: str, ranges: list[tuple[int, int]]) -> list[str]:
    blocks = split_paragraph_blocks(text)
    if not blocks:
        return [text] if text else []
    out: list[str] = []
    for start, end in ranges:
        s = max(0, int(start))
        e = min(len(blocks), int(end))
        if s < e:
            out.append("\n".join(blocks[s:e]))
    return out if out else [text]


def build_scan_chunk_plan(text: str) -> dict:
    """Persist at entity scan; replay on semantic scan with replaced preview text."""
    mode = os.getenv("DEID_LLM_CHUNK_MODE", "paragraph").strip().lower()
    if mode == "paragraph":
        ranges = chunk_paragraph_ranges(text)
        return {"mode": "paragraph", "ranges": [[s, e] for s, e in ranges]}
    return {"mode": mode, "count": count_llm_chunks(text)}


def apply_scan_chunk_plan(text: str, plan: dict | None) -> list[str]:
    if not plan:
        return build_llm_chunks(text)
    if plan.get("mode") == "paragraph" and plan.get("ranges"):
        ranges = [(int(r[0]), int(r[1])) for r in plan["ranges"]]
        return chunks_from_paragraph_ranges(text, ranges)
    return build_llm_chunks(text)


def _paragraph_chunk_ranges(
    blocks: list[str], chunk_size: int, overlap: int
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    buf: list[int] = []
    size = 0
    for idx, block in enumerate(blocks):
        blen = len(block) + 1
        if size + blen > chunk_size and buf:
            ranges.append((buf[0], buf[-1] + 1))
            tail_idx: list[int] = []
            tsize = 0
            for bi in reversed(buf):
                b = blocks[bi]
                if tsize + len(b) + 1 > overlap:
                    break
                tail_idx.insert(0, bi)
                tsize += len(b) + 1
            buf = tail_idx
            size = tsize
        buf.append(idx)
        size += blen
    if buf:
        ranges.append((buf[0], buf[-1] + 1))
    return ranges if ranges else [(0, len(blocks))]


def _chunk_text_fixed(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _chunk_text_paragraphs(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split on paragraph boundaries to keep tables/lists intact for the model."""
    blocks = split_paragraph_blocks(text)
    if not blocks:
        return [text]
    ranges = _paragraph_chunk_ranges(blocks, chunk_size, overlap)
    return ["\n".join(blocks[s:e]) for s, e in ranges]


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    mode = os.getenv("DEID_LLM_CHUNK_MODE", "paragraph").strip().lower()
    if mode == "fixed":
        return _chunk_text_fixed(text, chunk_size, overlap)
    return _chunk_text_paragraphs(text, chunk_size, overlap)


def _extract_json(content: str) -> dict:
    """Legacy helper — prefer parse_llm_entities."""
    from app.deid.discovery.llm_parse import parse_json_entities

    items = parse_json_entities(content)
    return {"entities": items}


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 2)


@dataclass
class LlmDiscoveryResult:
    entities: list[DiscoveredEntity] = field(default_factory=list)
    chunks: int = 0
    skipped: str | None = None
    worker_model: str | None = None
    errors: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_ms: int = 0


def _merge_entity(
    seen: dict[str, DiscoveredEntity],
    item: dict,
    text_norm: str,
    allowed_types: frozenset[str],
) -> tuple[DiscoveredEntity | None, bool]:
    """Returns (entity, is_new). is_new=False when deduped into an existing entry."""
    name = str(item.get("canonical_name") or "").strip()
    if is_invalid_entity_name(name):
        return None, False
    etype = str(item.get("entity_type") or "company")
    if etype not in allowed_types:
        etype = "company" if "company" in allowed_types else next(iter(allowed_types))
    aliases = [
        str(a).strip()
        for a in (item.get("aliases") or [])
        if a and not is_invalid_entity_name(str(a))
    ]
    if name not in aliases:
        aliases.insert(0, name)
    confidence = item.get("confidence")
    try:
        conf_f = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        conf_f = None
    hits = sum(text_norm.count(normalize_for_match(a)) for a in aliases if a)
    if hits == 0:
        hits = 1
    key = normalize_for_match(name)
    if key in seen:
        ent = seen[key]
        ent.hit_count = max(ent.hit_count, hits)
        if conf_f is not None and (ent.confidence is None or conf_f > ent.confidence):
            ent.confidence = conf_f
        for a in aliases:
            if a not in ent.aliases:
                ent.aliases.append(a)
        return ent, False
    ent = DiscoveredEntity(
        canonical_name=name,
        entity_type=etype,
        source="llm",
        aliases=aliases,
        hit_count=hits,
        confidence=conf_f,
    )
    seen[key] = ent
    return ent, True


async def discover_llm(
    sample: str,
    router: Any | None,
    *,
    job_id: int,
    db: Any | None = None,
    flow_id: str = "entity_scan",
    system_prompt: str | None = None,
    enabled: bool | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
    valid_entity_types: frozenset[str] | None = None,
    build_user_message: Callable[..., str] | None = None,
) -> LlmDiscoveryResult:
    result = LlmDiscoveryResult()
    started = time.monotonic()

    def emit(event: dict) -> None:
        if on_event:
            on_event(event)

    if enabled is None:
        enabled = os.getenv("DEID_LLM_ENABLED", "1").strip().lower() not in ("0", "false", "off")
    if not enabled:
        result.skipped = "llm_disabled"
        return result
    if not router or not router.session:
        result.skipped = "worker_offline"
        return result
    if router.session.state != "ready":
        result.skipped = f"worker_{router.session.state}"
        return result

    chunk_size, overlap = get_llm_chunk_params()
    timeout = float(os.getenv("DEID_LLM_TIMEOUT_SEC", "180"))
    model = os.getenv("DEID_LLM_MODEL") or router.session.model
    token_emit_interval = float(os.getenv("DEID_LLM_TOKEN_EMIT_SEC", "0.08"))

    result.worker_model = model
    chunks = _chunk_text(sample, chunk_size, overlap)
    result.chunks = len(chunks)
    text_norm = normalize_for_match(sample)
    seen: dict[str, DiscoveredEntity] = {}
    allowed_types = valid_entity_types or frozenset({"company", "person", "id", "org", "custom"})
    prompt = (system_prompt or build_default_scan_prompt()).strip()

    use_stream = os.getenv("DEID_LLM_STREAM", "0").strip().lower() in ("1", "true", "yes")

    for idx, chunk in enumerate(chunks):
        if on_progress:
            on_progress(idx + 1, len(chunks))
        emit({"type": "chunk_start", "index": idx + 1, "total": len(chunks)})
        emit({"type": "log", "line": f"开始分析第 {idx + 1}/{len(chunks)} 段…"})

        user_content = (
            build_user_message(chunk, index=idx + 1, total=len(chunks))
            if build_user_message
            else build_scan_user_message(chunk, index=idx + 1, total=len(chunks))
        )
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            "reasoning_effort": "none",
            "temperature": 0,
            "max_tokens": worker_max_tokens(),
        }
        if use_stream:
            body["stream"] = True
        req_id = f"{flow_id}-{job_id}-{idx}"
        chunk_prompt_est = _estimate_tokens(prompt) + _estimate_tokens(user_content)
        content = ""
        chunk_started = time.monotonic()
        call_error: str | None = None
        usage_prompt = chunk_prompt_est
        usage_completion = 0
        parsed_count = 0

        try:
            if use_stream:
                buffer_parts: list[str] = []
                pending_token = ""
                last_emit = time.monotonic()
                async for token in router.chat_completions_stream(
                    body, request_id=req_id, timeout=timeout
                ):
                    buffer_parts.append(token)
                    pending_token += token
                    now = time.monotonic()
                    if now - last_emit >= token_emit_interval and pending_token:
                        emit({"type": "token", "content": pending_token})
                        pending_token = ""
                        last_emit = now
                if pending_token:
                    emit({"type": "token", "content": pending_token})
                content = "".join(buffer_parts)
                usage_prompt = chunk_prompt_est
                usage_completion = _estimate_tokens(content)
                result.prompt_tokens += usage_prompt
                result.completion_tokens += usage_completion
            else:
                resp = await router.chat_completions(
                    body, request_id=req_id, timeout=timeout
                )
                choices = resp.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content") or ""
                usage = resp.get("usage") or {}
                usage_prompt = int(usage.get("prompt_tokens") or chunk_prompt_est)
                usage_completion = int(
                    usage.get("completion_tokens") or _estimate_tokens(content)
                )
                result.prompt_tokens += usage_prompt
                result.completion_tokens += usage_completion
                if content:
                    emit({"type": "token", "content": content})
        except WorkerOffline:
            result.skipped = "worker_offline"
            call_error = "worker_offline"
            _record_discover_call(
                db,
                job_id=job_id,
                flow_id=flow_id,
                request_id=req_id,
                chunk_index=idx + 1,
                chunk_total=len(chunks),
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
            _record_discover_call(
                db,
                job_id=job_id,
                flow_id=flow_id,
                request_id=req_id,
                chunk_index=idx + 1,
                chunk_total=len(chunks),
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
            emit({"type": "log", "line": f"第 {idx + 1} 段请求失败 (HTTP {exc.status})"})
            _record_discover_call(
                db,
                job_id=job_id,
                flow_id=flow_id,
                request_id=req_id,
                chunk_index=idx + 1,
                chunk_total=len(chunks),
                model=model,
                system_prompt=prompt,
                user_message=user_content,
                response=content or None,
                error=call_error,
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                parsed_count=0,
                elapsed_ms=int((time.monotonic() - chunk_started) * 1000),
            )
            continue
        except Exception as exc:
            call_error = type(exc).__name__
            result.errors.append(f"chunk {idx}: {type(exc).__name__}")
            emit({"type": "log", "line": f"第 {idx + 1} 段异常: {type(exc).__name__}"})
            _record_discover_call(
                db,
                job_id=job_id,
                flow_id=flow_id,
                request_id=req_id,
                chunk_index=idx + 1,
                chunk_total=len(chunks),
                model=model,
                system_prompt=prompt,
                user_message=user_content,
                response=content or None,
                error=call_error,
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                parsed_count=0,
                elapsed_ms=int((time.monotonic() - chunk_started) * 1000),
            )
            continue

        items, fmt = parse_llm_entities(content, allowed_types)
        if fmt == "none":
            preview = content.strip().replace("\n", " ")[:120]
            result.errors.append(f"chunk {idx}: unparseable")
            emit(
                {
                    "type": "log",
                    "line": f"第 {idx + 1} 段未能解析（模型返回：{preview or '空'}…）",
                }
            )
            _record_discover_call(
                db,
                job_id=job_id,
                flow_id=flow_id,
                request_id=req_id,
                chunk_index=idx + 1,
                chunk_total=len(chunks),
                model=model,
                system_prompt=prompt,
                user_message=user_content,
                response=content,
                error="unparseable",
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                parsed_count=0,
                elapsed_ms=int((time.monotonic() - chunk_started) * 1000),
            )
            continue

        found_in_chunk = 0
        for item in items:
            ent, is_new = _merge_entity(seen, item, text_norm, allowed_types)
            if ent and is_new:
                found_in_chunk += 1
                emit(
                    {
                        "type": "entity",
                        "name": ent.canonical_name,
                        "entity_type": ent.entity_type,
                        "source": "llm",
                    }
                )
        parsed_count = found_in_chunk
        emit(
            {
                "type": "log",
                "line": f"第 {idx + 1} 段完成（{fmt}），本段发现 {found_in_chunk} 个实体",
            }
        )
        _record_discover_call(
            db,
            job_id=job_id,
            flow_id=flow_id,
            request_id=req_id,
            chunk_index=idx + 1,
            chunk_total=len(chunks),
            model=model,
            system_prompt=prompt,
            user_message=user_content,
            response=content,
            error=None,
            prompt_tokens=usage_prompt,
            completion_tokens=usage_completion,
            parsed_count=parsed_count,
            elapsed_ms=int((time.monotonic() - chunk_started) * 1000),
        )

    result.entities = list(seen.values())
    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    emit(
        {
            "type": "metrics",
            "elapsed_ms": result.elapsed_ms,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "model": model,
        }
    )
    return result


def _record_discover_call(db: Any | None, **kwargs) -> None:
    from app.deid.discovery.flows import _maybe_record_worker_call

    _maybe_record_worker_call(db, **kwargs)
