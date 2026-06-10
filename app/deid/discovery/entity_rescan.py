"""Entity scan: initial discovery and user-triggered re-scan."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.deid.discovery.chunk_entities import entities_in_chunk, format_entity_list
from app.deid.discovery.enrich import enrich_discovered_entities
from app.deid.discovery.experience_store import build_experience_prompt_block
from app.deid.discovery.llm import LlmDiscoveryResult, discover_llm
from app.deid.discovery.merge import MergedEntity, merge_entities
from app.deid.discovery.rules import DiscoveredEntity
from app.deid.engine.plan import normalize_for_match
from app.deid.prompts import build_re_discover_user_message, build_scan_user_message


def snapshot_entities(entities: list[MergedEntity]) -> list[dict]:
    return [
        {
            "canonical_name": e.canonical_name,
            "entity_type": e.entity_type,
            "aliases": list(e.aliases or []),
        }
        for e in entities
    ]


def _canonical_keys(entities: list[MergedEntity] | list[dict]) -> set[str]:
    keys: set[str] = set()
    for e in entities:
        if isinstance(e, dict):
            name = e.get("canonical_name") or ""
        else:
            name = e.canonical_name
        k = normalize_for_match(name)
        if k:
            keys.add(k)
    return keys


def diff_canonical_vs_initial(
    initial_snapshot: list[dict],
    current: list[MergedEntity],
) -> list[str]:
    initial_keys = _canonical_keys(initial_snapshot)
    out: list[str] = []
    for ent in current:
        k = normalize_for_match(ent.canonical_name)
        if k and k not in initial_keys:
            out.append(ent.canonical_name)
    return out


def diff_canonical_new_in_round(
    before: list[MergedEntity],
    after: list[MergedEntity],
) -> list[str]:
    before_keys = _canonical_keys(before)
    out: list[str] = []
    for ent in after:
        if ent.source != "llm":
            continue
        k = normalize_for_match(ent.canonical_name)
        if k and k not in before_keys:
            out.append(ent.canonical_name)
    return out


def _discovered_to_merged(entities: list[DiscoveredEntity]) -> list[MergedEntity]:
    return [
        MergedEntity(
            canonical_name=e.canonical_name,
            entity_type=e.entity_type,
            source=e.source,
            aliases=e.aliases or [e.canonical_name],
            hit_count=e.hit_count,
            confidence=e.confidence,
        )
        for e in entities
    ]


def build_initial_system_prompt(base_prompt: str, exp_lines: list[str] | None) -> str:
    block = build_experience_prompt_block(exp_lines)
    return f"{base_prompt.strip()}{block}"


@dataclass
class InitialScanResult:
    entities: list[MergedEntity]
    llm_result: LlmDiscoveryResult | None


@dataclass
class ReScanResult:
    entities: list[MergedEntity]
    llm_result: LlmDiscoveryResult | None
    new_canonicals: list[str]


async def run_initial_scan(
    sample: str,
    base_entities: list[MergedEntity],
    router,
    db,
    *,
    job_id: int,
    system_prompt: str,
    valid_entity_types: frozenset[str],
    exp_lines: list[str] | None = None,
    on_progress: Callable | None = None,
    on_event: Callable | None = None,
) -> InitialScanResult:
    prompt = build_initial_system_prompt(system_prompt, exp_lines)
    llm_result = await discover_llm(
        sample,
        router,
        job_id=job_id,
        db=db,
        flow_id="entity_scan",
        system_prompt=prompt,
        enabled=True,
        on_progress=on_progress,
        on_event=on_event,
        valid_entity_types=valid_entity_types,
        build_user_message=build_scan_user_message,
    )
    combined_raw = list(llm_result.entities)
    if sample and combined_raw:
        enrich_discovered_entities(sample, combined_raw)
    round_entities = _discovered_to_merged(combined_raw)
    merged = merge_entities(base_entities + round_entities)
    return InitialScanResult(entities=merged, llm_result=llm_result)


async def run_re_scan(
    sample: str,
    base_entities: list[MergedEntity],
    router,
    db,
    *,
    job_id: int,
    re_discover_prompt: str,
    valid_entity_types: frozenset[str],
    on_progress: Callable | None = None,
    on_event: Callable | None = None,
) -> ReScanResult:
    before = list(base_entities)

    def build_user(chunk: str, *, index: int, total: int) -> str:
        subset = entities_in_chunk(chunk, base_entities)
        known = format_entity_list(subset) if subset else "（暂无）"
        return build_re_discover_user_message(
            chunk,
            known_entities=known,
            index=index,
            total=total,
        )

    llm_result = await discover_llm(
        sample,
        router,
        job_id=job_id,
        db=db,
        flow_id="re_discover",
        system_prompt=re_discover_prompt,
        enabled=True,
        on_progress=on_progress,
        on_event=on_event,
        valid_entity_types=valid_entity_types,
        build_user_message=build_user,
    )
    combined_raw = list(llm_result.entities)
    if sample and combined_raw:
        enrich_discovered_entities(sample, combined_raw)
    round_entities = _discovered_to_merged(combined_raw)
    merged = merge_entities(base_entities + round_entities)
    new_canonicals = diff_canonical_new_in_round(before, merged)
    return ReScanResult(
        entities=merged,
        llm_result=llm_result,
        new_canonicals=new_canonicals,
    )
