"""Document-level entity discovery rules (以下简称 only)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.deid.engine.plan import normalize_for_match


@dataclass
class DiscoveredEntity:
    canonical_name: str
    entity_type: str
    source: str
    aliases: list[str] = field(default_factory=list)
    hit_count: int = 0
    confidence: float | None = None


_HEREAFTER_RE = re.compile(
    r"(.{2,60}?)[（(]以下简称[「\"']([^」\"']+)[」\"']",
    re.UNICODE,
)
_HEREAFTER_ALT_RE = re.compile(
    r"(.{2,60}?)[（(]下称[「\"']([^」\"']+)[」\"']",
    re.UNICODE,
)


def _count_hits(text_norm: str, alias: str) -> int:
    na = normalize_for_match(alias)
    if not na:
        return 0
    return text_norm.count(na)


def discover_hereafter_rules(sample: str, text_norm: str) -> list[DiscoveredEntity]:
    """Match 以下简称 / 下称 patterns; canonical=full name, aliases=short names."""
    found: dict[str, DiscoveredEntity] = {}
    for pattern in (_HEREAFTER_RE, _HEREAFTER_ALT_RE):
        for m in pattern.finditer(sample):
            full_name = m.group(1).strip()
            short_name = m.group(2).strip()
            if len(full_name) < 2 or len(short_name) < 2:
                continue
            if full_name == short_name:
                continue
            hits = max(
                _count_hits(text_norm, full_name),
                _count_hits(text_norm, short_name),
            )
            if hits == 0:
                continue
            key = normalize_for_match(full_name)
            if key not in found:
                found[key] = DiscoveredEntity(
                    canonical_name=full_name,
                    entity_type="company",
                    source="rule",
                    aliases=[short_name],
                    hit_count=hits,
                )
            else:
                ent = found[key]
                ent.hit_count = max(ent.hit_count, hits)
                if short_name not in ent.aliases:
                    ent.aliases.append(short_name)
    return list(found.values())
