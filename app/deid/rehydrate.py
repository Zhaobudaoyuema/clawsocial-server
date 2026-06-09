"""Restore original entity names from placeholder tokens (rehydration)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")


class MappingRow(Protocol):
    placeholder: str
    original_text: str


@dataclass(frozen=True)
class RehydrateResult:
    text: str
    resolved: list[str]
    unresolved: list[str]


def bare_from_bracketed(ph: str) -> str | None:
    ph = (ph or "").strip()
    if ph.startswith("[") and ph.endswith("]") and len(ph) > 2:
        return ph[1:-1]
    return None


def bracket_from_bare(token: str) -> str:
    return f"[{token}]"


def build_placeholder_map(rows: list[MappingRow]) -> dict[str, str]:
    """placeholder -> original_text; prefer longest alias per placeholder."""
    buckets: dict[str, list[str]] = {}
    for row in rows:
        ph = (row.placeholder or "").strip()
        orig = (row.original_text or "").strip()
        if not ph or not orig:
            continue
        buckets.setdefault(ph, []).append(orig)
    return {ph: max(texts, key=len) for ph, texts in buckets.items()}


def expand_placeholder_map(ph_map: dict[str, str]) -> dict[str, str]:
    """Add bare aliases (公司_1) for bracketed keys ([公司_1])."""
    expanded = dict(ph_map)
    for ph, orig in ph_map.items():
        bare = bare_from_bracketed(ph)
        if bare and bare not in expanded:
            expanded[bare] = orig
    return expanded


def canonical_placeholder(token: str, ph_map: dict[str, str]) -> str:
    if token in ph_map:
        return token
    bare = bare_from_bracketed(token)
    if bare and bracket_from_bare(bare) in ph_map:
        return bracket_from_bare(bare)
    if bracket_from_bare(token) in ph_map:
        return bracket_from_bare(token)
    return token


def find_bracketed_placeholders(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in PLACEHOLDER_RE.finditer(text):
        token = m.group(0)
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _placeholder_prefixes(ph_map: dict[str, str]) -> list[str]:
    prefixes: set[str] = set()
    for ph in ph_map:
        bare = bare_from_bracketed(ph) or ph
        if "_" in bare:
            prefixes.add(bare.rsplit("_", 1)[0])
    return sorted(prefixes, key=len, reverse=True)


def find_bare_placeholders(text: str, ph_map: dict[str, str]) -> list[str]:
    """Find bare 公司_1 tokens using known mapping prefixes."""
    seen: set[str] = set()
    out: list[str] = []
    for prefix in _placeholder_prefixes(ph_map):
        pat = re.compile(rf"{re.escape(prefix)}_\d+")
        for m in pat.finditer(text):
            token = m.group(0)
            start, end = m.start(), m.end()
            if start > 0 and end < len(text) and text[start - 1] == "[" and text[end] == "]":
                continue
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def find_placeholders_in_text(text: str, ph_map: dict[str, str] | None = None) -> list[str]:
    ph_map = ph_map or {}
    return find_bracketed_placeholders(text) + find_bare_placeholders(text, ph_map)


def rehydrate_text(text: str, ph_map: dict[str, str]) -> RehydrateResult:
    """Replace known placeholders; longest tokens first to avoid partial overlap."""
    if not text:
        return RehydrateResult(text="", resolved=[], unresolved=[])

    expanded = expand_placeholder_map(ph_map)
    result = text
    resolved_set: set[str] = set()
    for ph in sorted(expanded.keys(), key=len, reverse=True):
        if ph in result:
            result = result.replace(ph, expanded[ph])
            resolved_set.add(canonical_placeholder(ph, ph_map))

    unresolved: list[str] = []
    for token in find_bracketed_placeholders(text):
        if token not in expanded:
            unresolved.append(token)
    for token in find_bare_placeholders(text, ph_map):
        if token not in expanded:
            unresolved.append(token)

    return RehydrateResult(
        text=result,
        resolved=sorted(resolved_set),
        unresolved=unresolved,
    )
