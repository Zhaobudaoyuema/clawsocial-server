"""Worker flow: scan_experience — one global lesson from chunk entity diffs."""
from __future__ import annotations

import json

from app.deid.discovery.chunk_entities import entities_in_chunk
from app.deid.discovery.flow_parse import parse_exp_lines
from app.deid.discovery.flows import FlowItem, default_chunk_user_message, run_worker_flow
from app.deid.discovery.llm import _chunk_text, get_llm_chunk_params
from app.deid.discovery.merge import MergedEntity
from app.deid.engine.plan import normalize_for_match
from app.deid.prompts import FLOW_SCAN_EXPERIENCE_KEY
from app.deid.settings_store import get_flow_prompt


def _entities_subset_dict(entities: list[MergedEntity]) -> list[dict]:
    return [
        {"canonical_name": e.canonical_name, "entity_type": e.entity_type}
        for e in entities
    ]


def _filter_snapshot_for_chunk(chunk: str, snapshot: list[dict]) -> list[dict]:
    norm_chunk = normalize_for_match(chunk)
    if not norm_chunk:
        return []
    out: list[dict] = []
    for item in snapshot:
        names = [item.get("canonical_name") or ""] + list(item.get("aliases") or [])
        if any(normalize_for_match(n) in norm_chunk for n in names if n):
            out.append(item)
    return out


def build_chunk_diff_payload(
    sample: str,
    initial_snapshot: list[dict],
    current_entities: list[MergedEntity],
    *,
    max_chars: int = 4000,
) -> str:
    chunk_size, overlap = get_llm_chunk_params()
    chunks = _chunk_text(sample, chunk_size, overlap)
    rows: list[dict] = []
    for chunk in chunks:
        initial_subset = _filter_snapshot_for_chunk(chunk, initial_snapshot)
        current_subset = _entities_subset_dict(entities_in_chunk(chunk, current_entities))
        initial_keys = {normalize_for_match(x["canonical_name"]) for x in initial_subset}
        added = [
            x["canonical_name"]
            for x in current_subset
            if normalize_for_match(x["canonical_name"]) not in initial_keys
        ]
        if not added and len(current_subset) <= len(initial_subset):
            continue
        rows.append(
            {
                "initial": [x["canonical_name"] for x in initial_subset],
                "current": [x["canonical_name"] for x in current_subset],
                "added": added,
            }
        )
    text = json.dumps(rows, ensure_ascii=False)
    if len(text) > max_chars:
        return text[:max_chars]
    return text


async def run_scan_experience(
    sample: str,
    initial_snapshot: list[dict],
    current_entities: list[MergedEntity],
    router,
    db,
    *,
    job_id: int,
    on_event=None,
) -> str | None:
    if not sample or not router:
        return None

    payload = build_chunk_diff_payload(sample, initial_snapshot, current_entities)
    if not payload or payload == "[]":
        return None

    prompt = get_flow_prompt(db, FLOW_SCAN_EXPERIENCE_KEY)
    unit = FlowItem(text=payload, meta={})

    def build_user(unit: FlowItem, index: int, total: int) -> str:
        head = default_chunk_user_message(unit, index, total)
        return f"{head}\n\n【各片段实体差异】\n{unit.text}"

    def parse_chunk(content: str, unit: FlowItem) -> list[str]:
        return parse_exp_lines(content)

    result = await run_worker_flow(
        "scan_experience",
        [unit],
        router,
        job_id=job_id,
        db=db,
        system_prompt=prompt,
        build_user_message=build_user,
        parse_chunk=parse_chunk,
        on_event=on_event,
    )
    if result.skipped or not result.items:
        return None
    line = str(result.items[0]).strip()[:100]
    return line or None
