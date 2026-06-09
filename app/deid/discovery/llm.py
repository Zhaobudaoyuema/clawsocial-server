"""LLM-based entity discovery via Mac Worker / Ollama."""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.deid.discovery.rules import DiscoveredEntity
from app.deid.engine.plan import normalize_for_match
from app.deid.prompts import DEFAULT_SCAN_PROMPT
from app.deid.worker.errors import WorkerBusy, WorkerOffline, WorkerRequestError
from app.deid.worker.router import WorkerRouter

def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
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


def _extract_json(content: str) -> dict:
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if fence:
        content = fence.group(1).strip()
    return json.loads(content)


@dataclass
class LlmDiscoveryResult:
    entities: list[DiscoveredEntity] = field(default_factory=list)
    chunks: int = 0
    skipped: str | None = None
    worker_model: str | None = None
    errors: list[str] = field(default_factory=list)


async def discover_llm(
    sample: str,
    router: WorkerRouter | None,
    *,
    job_id: int,
    system_prompt: str | None = None,
    enabled: bool | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    valid_entity_types: frozenset[str] | None = None,
) -> LlmDiscoveryResult:
    result = LlmDiscoveryResult()
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

    chunk_size = int(os.getenv("DEID_LLM_CHUNK_SIZE", "6000"))
    overlap = int(os.getenv("DEID_LLM_CHUNK_OVERLAP", "500"))
    timeout = float(os.getenv("DEID_LLM_TIMEOUT_SEC", "120"))
    model = os.getenv("DEID_LLM_MODEL") or router.session.model

    result.worker_model = model
    chunks = _chunk_text(sample, chunk_size, overlap)
    result.chunks = len(chunks)
    text_norm = normalize_for_match(sample)
    seen: dict[str, DiscoveredEntity] = {}
    allowed_types = valid_entity_types or frozenset({"company", "person", "id", "org", "custom"})

    prompt = (system_prompt or DEFAULT_SCAN_PROMPT).strip()

    for idx, chunk in enumerate(chunks):
        if on_progress:
            on_progress(idx + 1, len(chunks))
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": chunk},
            ],
            "stream": False,
            "reasoning_effort": "none",
            "temperature": 0,
            "max_tokens": 4096,
        }
        req_id = f"scan-{job_id}-{idx}"
        try:
            resp_body = await router.chat_completions(body, request_id=req_id, timeout=timeout)
        except WorkerOffline:
            result.skipped = "worker_offline"
            break
        except WorkerBusy as exc:
            result.skipped = str(exc)
            break
        except WorkerRequestError as exc:
            result.errors.append(f"chunk {idx}: status {exc.status}")
            continue
        except Exception as exc:
            result.errors.append(f"chunk {idx}: {type(exc).__name__}")
            continue

        try:
            choices = resp_body.get("choices") or []
            content = choices[0]["message"]["content"] if choices else ""
            parsed = _extract_json(content)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            result.errors.append(f"chunk {idx}: invalid_json")
            continue

        for item in parsed.get("entities") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("canonical_name") or "").strip()
            if not name or len(name) > 200:
                continue
            etype = str(item.get("entity_type") or "company")
            if etype not in allowed_types:
                etype = "company" if "company" in allowed_types else next(iter(allowed_types))
            aliases = [str(a).strip() for a in (item.get("aliases") or []) if a]
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
            else:
                seen[key] = DiscoveredEntity(
                    canonical_name=name,
                    entity_type=etype,
                    source="llm",
                    aliases=aliases,
                    hit_count=hits,
                    confidence=conf_f,
                )

    result.entities = list(seen.values())
    return result
