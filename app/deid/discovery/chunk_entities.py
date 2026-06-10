"""Helpers: map entities to document chunks."""
from __future__ import annotations

from app.deid.discovery.merge import MergedEntity
from app.deid.engine.plan import normalize_for_match


def entities_in_chunk(chunk: str, entities: list[MergedEntity]) -> list[MergedEntity]:
    norm_chunk = normalize_for_match(chunk)
    if not norm_chunk:
        return []
    hits: list[MergedEntity] = []
    for ent in entities:
        names = [ent.canonical_name, *(ent.aliases or [])]
        if any(normalize_for_match(n) in norm_chunk for n in names if n):
            hits.append(ent)
    return hits


def format_entity_list(entities: list[MergedEntity]) -> str:
    lines: list[str] = []
    for ent in entities[:40]:
        aliases = [a for a in (ent.aliases or []) if a != ent.canonical_name]
        alias_part = "|".join(aliases[:5]) if aliases else ""
        if alias_part:
            lines.append(f"{ent.canonical_name}|{alias_part}")
        else:
            lines.append(ent.canonical_name)
    return "\n".join(lines)
