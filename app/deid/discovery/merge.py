"""Merge and deduplicate discovered entities across sources."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.deid.engine.plan import normalize_for_match

SOURCE_PRIORITY = {
    "manual": 0,
    "preset": 1,
    "rule": 2,
    "leak_verify": 3,
    "llm": 4,
}

# Generic fragments must not trigger cross-entity merge (enrich may add these).
_GENERIC_MERGE = frozenset(
    {
        "股份",
        "有限公司",
        "股份有限公司",
        "科技股份",
        "科技公司",
        "集团",
        "集团公司",
        "公司",
        "有限",
        "企业",
        "股份有限",
        "控股",
        "投资",
        "管理",
        "合伙企业",
        "有限合伙",
    }
)
_STOCK_CODE = re.compile(r"^\d{5,6}\.[A-Z]{2}$|^\d+\.[A-Z]{2,4}$|^[A-Z0-9]{2,12}$", re.I)


def _is_mergeable_name(name: str) -> bool:
    n = name.strip()
    if not n:
        return False
    norm = normalize_for_match(n)
    if len(norm) < 2:
        return False
    if _STOCK_CODE.match(norm):
        return True
    if len(norm) < 4:
        return False
    if n in _GENERIC_MERGE or norm in _GENERIC_MERGE:
        return False
    return True


@dataclass
class MergedEntity:
    canonical_name: str
    entity_type: str
    source: str
    aliases: list[str] = field(default_factory=list)
    hit_count: int = 0
    library_entity_id: int | None = None
    confidence: float | None = None


def _merge_keys(ent: MergedEntity) -> list[str]:
    """Names that may link two distinct discoveries of the same real-world entity."""
    keys: list[str] = []
    ck = normalize_for_match(ent.canonical_name)
    if ck:
        keys.append(ck)
    for alias in ent.aliases:
        if alias == ent.canonical_name:
            continue
        if not _is_mergeable_name(alias):
            continue
        ak = normalize_for_match(alias)
        if ak and ak not in keys:
            keys.append(ak)
    return keys


def merge_entities(entities: list[MergedEntity]) -> list[MergedEntity]:
    """Deduplicate same entity from different sources; never collapse unrelated names."""
    if not entities:
        return []

    index: dict[str, int] = {}
    merged: list[MergedEntity] = []

    def find_match(ent: MergedEntity) -> int | None:
        for key in _merge_keys(ent):
            idx = index.get(key)
            if idx is not None:
                return idx
        return None

    def register_keys(idx: int, ent: MergedEntity) -> None:
        for key in _merge_keys(ent):
            index[key] = idx

    for ent in sorted(entities, key=lambda e: SOURCE_PRIORITY.get(e.source, 99)):
        match_idx = find_match(ent)
        if match_idx is None:
            merged.append(
                MergedEntity(
                    canonical_name=ent.canonical_name,
                    entity_type=ent.entity_type,
                    source=ent.source,
                    aliases=list(dict.fromkeys(ent.aliases)),
                    hit_count=ent.hit_count,
                    library_entity_id=ent.library_entity_id,
                    confidence=ent.confidence,
                )
            )
            register_keys(len(merged) - 1, merged[-1])
            continue

        target = merged[match_idx]
        if SOURCE_PRIORITY.get(ent.source, 99) < SOURCE_PRIORITY.get(target.source, 99):
            target.source = ent.source
        if ent.library_entity_id and not target.library_entity_id:
            target.library_entity_id = ent.library_entity_id
        if len(ent.canonical_name) > len(target.canonical_name):
            old_canonical = target.canonical_name
            target.canonical_name = ent.canonical_name
            if old_canonical not in target.aliases:
                target.aliases.append(old_canonical)
        target.hit_count = max(target.hit_count, ent.hit_count)
        if ent.confidence is not None:
            if target.confidence is None or ent.confidence > target.confidence:
                target.confidence = ent.confidence
        for alias in ent.aliases:
            if alias != target.canonical_name and alias not in target.aliases:
                target.aliases.append(alias)
        register_keys(match_idx, target)

    return merged
