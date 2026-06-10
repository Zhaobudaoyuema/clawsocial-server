"""Entity leak detection during scan — Worker verify on preview text."""
from __future__ import annotations

import re
from collections.abc import Callable

from app.deid.discovery.merge import MergedEntity, merge_entities
from app.deid.discovery.standard_verify import run_post_run_verify
from app.deid.engine.plan import normalize_for_match

_STOCK_CODE = re.compile(r"^\d{5,6}\.[A-Z]{2,4}$", re.I)
_ORG_HINT = re.compile(
    r"(?:集团|设计院|有限公司|股份有限公司|有限责任公司|事务所|中心|有限合伙)"
)
_PLACEHOLDER = re.compile(r"\[(?:公司|姓名|机构|实体|人物)_\d+\]")


def _snippet_to_entity(snippet: str, text_norm: str) -> MergedEntity | None:
    s = snippet.strip()
    if not s or len(s) < 2:
        return None
    if _PLACEHOLDER.search(s):
        return None
    if _STOCK_CODE.match(s.replace(" ", "")):
        return None
    if not _ORG_HINT.search(s) and len(s) < 6:
        return None
    if "同花顺" in s or re.search(r"(?i)wind", s):
        return None
    hits = text_norm.count(normalize_for_match(s))
    if hits == 0:
        return None
    return MergedEntity(
        canonical_name=s,
        entity_type="company",
        source="leak_verify",
        aliases=[s],
        hit_count=hits,
    )


def leaks_to_entities(leaks: list[dict], sample: str) -> list[MergedEntity]:
    """Convert entity_leak Worker findings into mergeable entities."""
    text_norm = normalize_for_match(sample)
    out: list[MergedEntity] = []
    seen: set[str] = set()
    for leak in leaks:
        if (leak.get("category") or "").lower() != "entity_leak":
            continue
        snippet = (leak.get("snippet") or "").strip()
        key = normalize_for_match(snippet)
        if not key or key in seen:
            continue
        ent = _snippet_to_entity(snippet, text_norm)
        if ent:
            seen.add(key)
            out.append(ent)
    return out


async def run_entity_leak_scan(
    preview_text: str,
    sample: str,
    base_entities: list[MergedEntity],
    router,
    db,
    *,
    job_id: int,
    job_extra: str | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> tuple[list[MergedEntity], list[dict], dict]:
    """
    Run post_run_verify on entity-replaced preview; merge entity_leak hits.

    Returns (merged_entities, leak_findings, summary).
    """
    leaks, summary = await run_post_run_verify(
        preview_text,
        router,
        db,
        job_id=job_id,
        job_extra=job_extra,
    )
    discovered = leaks_to_entities(leaks, sample)
    if on_event and discovered:
        on_event(
            {
                "type": "log",
                "line": f"实体验漏发现 {len(discovered)} 个字面残留",
            }
        )
    merged = merge_entities(base_entities + discovered) if discovered else base_entities
    return merged, leaks, summary
