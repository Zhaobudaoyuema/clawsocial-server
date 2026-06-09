"""Merge and deduplicate discovered entities across sources."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.deid.engine.plan import normalize_for_match

SOURCE_PRIORITY = {
    "manual": 0,
    "preset": 1,
    "rule": 2,
    "llm": 3,
    "pattern": 4,
}


@dataclass
class MergedEntity:
    canonical_name: str
    entity_type: str
    source: str
    aliases: list[str] = field(default_factory=list)
    hit_count: int = 0
    library_entity_id: int | None = None
    confidence: float | None = None


def _all_names(ent: MergedEntity) -> list[str]:
    names = [ent.canonical_name]
    names.extend(ent.aliases)
    return names


def merge_entities(entities: list[MergedEntity]) -> list[MergedEntity]:
    """Deduplicate by normalized alias; higher-priority source wins canonical."""
    if not entities:
        return []

    index: dict[str, int] = {}
    merged: list[MergedEntity] = []

    def find_match(name: str) -> int | None:
        key = normalize_for_match(name)
        if not key:
            return None
        return index.get(key)

    def register_names(idx: int, ent: MergedEntity) -> None:
        for name in _all_names(ent):
            key = normalize_for_match(name)
            if key:
                index[key] = idx

    for ent in sorted(entities, key=lambda e: SOURCE_PRIORITY.get(e.source, 99)):
        match_idx = None
        for name in _all_names(ent):
            idx = find_match(name)
            if idx is not None:
                match_idx = idx
                break
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
            register_names(len(merged) - 1, merged[-1])
            continue

        target = merged[match_idx]
        if SOURCE_PRIORITY.get(ent.source, 99) < SOURCE_PRIORITY.get(target.source, 99):
            target.source = ent.source
            if ent.library_entity_id:
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
        register_names(match_idx, target)

    return merged
