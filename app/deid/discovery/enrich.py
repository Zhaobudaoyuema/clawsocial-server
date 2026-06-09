"""Post-discovery enrichment: link aliases, propagate 以下简称, filter noise."""
from __future__ import annotations

import re

from app.deid.discovery.rules import DiscoveredEntity, discover_hereafter_rules
from app.deid.engine.plan import normalize_for_match

# Bond / note codes often embed issuer abbreviations (e.g. 25中能建MTN001)
_EMBEDDED_ABBR = re.compile(
    r"[\dA-Za-z\-]*([\u4e00-\u9fff]{2,10})(?:MTN|PPN|SCP|CP|EB|ABN|债|票据)",
    re.IGNORECASE,
)

# Skip generic tokens that are not organization names
_NOISE_TERMS = frozenset(
    {
        "同花顺",
        "wind",
        "东方财富",
        "企查查",
        "天眼查",
        "中国北京市",
        "中国上海市",
        "组织结构",
        "组织结构图",
    }
)


def _is_noise(name: str) -> bool:
    n = name.strip()
    if not n or len(n) < 2:
        return True
    if n in _NOISE_TERMS:
        return True
    if re.fullmatch(r"中国[\u4e00-\u9fff]{1,4}[省市县区]", n):
        return True
    return False


def _add_alias(ent: DiscoveredEntity, alias: str, text_norm: str) -> None:
    alias = alias.strip()
    if not alias or _is_noise(alias) or alias == ent.canonical_name:
        return
    if alias not in ent.aliases:
        ent.aliases.append(alias)
    hits = text_norm.count(normalize_for_match(alias))
    if hits:
        ent.hit_count = max(ent.hit_count, hits)


def propagate_hereafter(
    entities: list[DiscoveredEntity], sample: str, text_norm: str
) -> None:
    """Attach 以下简称 / 下称 short names to matching entities."""
    index: dict[str, DiscoveredEntity] = {}
    for ent in entities:
        index[normalize_for_match(ent.canonical_name)] = ent
        for a in ent.aliases:
            index[normalize_for_match(a)] = ent

    for pair in discover_hereafter_rules(sample, text_norm):
        full_key = normalize_for_match(pair.canonical_name)
        target = index.get(full_key)
        if not target:
            for key, ent in index.items():
                if full_key in key or key in full_key:
                    target = ent
                    break
        if not target:
            entities.append(pair)
            index[full_key] = pair
            for a in pair.aliases:
                index[normalize_for_match(a)] = pair
            continue
        _add_alias(target, pair.canonical_name, text_norm)
        for a in pair.aliases:
            _add_alias(target, a, text_norm)
        target.hit_count = max(target.hit_count, pair.hit_count)


def _chars_subsequence(short: str, long: str) -> bool:
    """True if all chars of short appear in order within long."""
    if not short:
        return False
    j = 0
    for c in long:
        if j < len(short) and c == short[j]:
            j += 1
    return j == len(short)


def propagate_embedded_abbreviations(
    entities: list[DiscoveredEntity], sample: str, text_norm: str
) -> None:
    """Link abbreviations found inside bond/product codes to known entities."""
    companies = [e for e in entities if e.entity_type in ("company", "org")]
    if not companies:
        return

    for m in _EMBEDDED_ABBR.finditer(sample):
        abbr = m.group(1).strip()
        if len(abbr) < 2 or _is_noise(abbr):
            continue
        if text_norm.count(normalize_for_match(abbr)) == 0:
            continue
        best: DiscoveredEntity | None = None
        best_score = 0
        for ent in companies:
            pool = [ent.canonical_name, *ent.aliases]
            for name in pool:
                score = 0
                if abbr in name or name in abbr:
                    score = len(abbr) + 10
                elif _chars_subsequence(abbr, name):
                    score = len(abbr) + 5
                elif _chars_subsequence(name[: min(6, len(name))], abbr):
                    score = len(abbr)
                if score > best_score:
                    best_score = score
                    best = ent
        if best and best_score >= len(abbr):
            _add_alias(best, abbr, text_norm)


def enrich_discovered_entities(
    sample: str, entities: list[DiscoveredEntity]
) -> list[DiscoveredEntity]:
    """Cross-link aliases using document context (no hardcoded company names)."""
    if not sample:
        return entities
    text_norm = normalize_for_match(sample)
    propagate_hereafter(entities, sample, text_norm)
    propagate_embedded_abbreviations(entities, sample, text_norm)
    kept = [e for e in entities if not _is_noise(e.canonical_name)]
    entities[:] = kept
    return entities
