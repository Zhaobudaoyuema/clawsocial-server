"""ReplacementPlan + normalize_for_match — shared by XML and docx engines."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field


def normalize_for_match(text: str) -> str:
    """NFKC + collapse whitespace for scan/replace matching."""
    t = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", t)


def build_norm_index(text: str) -> tuple[str, list[int]]:
    """Normalized text + original char index per normalized char."""
    orig_indices: list[int] = []
    parts: list[str] = []
    for i, ch in enumerate(text):
        nc = normalize_for_match(ch)
        if nc:
            parts.append(nc)
            orig_indices.append(i)
    return "".join(parts), orig_indices


@dataclass
class MatchSpan:
    start: int
    end: int
    original: str
    replacement: str
    entity_type: str
    source: str  # preset / manual / pattern


@dataclass
class _PreparedNeedle:
    norm: str
    replacement: str
    entity_type: str
    source: str


@dataclass
class ReplacementPlan:
    """Build replacement spans from aliases, patterns, and whitelist."""

    whitelist_protected: list[tuple[int, int]] = field(default_factory=list)
    spans: list[MatchSpan] = field(default_factory=list)
    placeholder_map: dict[str, str] = field(default_factory=dict)  # canonical -> placeholder
    stats_whitelist_skips: int = 0
    _prepared: list[_PreparedNeedle] = field(default_factory=list, repr=False)
    _needles_by_char: dict[str, list[_PreparedNeedle]] = field(default_factory=dict, repr=False)
    _finalized: bool = field(default=False, repr=False)

    def finalize(self) -> None:
        if self._finalized:
            return
        seen: set[str] = set()
        prepared: list[_PreparedNeedle] = []
        for span in self.spans:
            norm = normalize_for_match(span.original)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            prepared.append(
                _PreparedNeedle(
                    norm=norm,
                    replacement=span.replacement,
                    entity_type=span.entity_type,
                    source=span.source,
                )
            )
        prepared.sort(key=lambda p: len(p.norm), reverse=True)
        self._prepared = prepared
        buckets: dict[str, list[_PreparedNeedle]] = defaultdict(list)
        for pn in prepared:
            buckets[pn.norm[0]].append(pn)
        self._needles_by_char = dict(buckets)
        self._finalized = True

    def apply_to_text(self, text: str) -> tuple[str, int]:
        """Return (new_text, replacement_count) for a single paragraph."""
        if not self.spans or not text:
            return text, 0
        if not self._finalized:
            self.finalize()
        norm_text, orig_indices = build_norm_index(text)
        if not norm_text or not self._prepared:
            return text, 0
        applicable = self._find_spans_in_original(text, norm_text, orig_indices)
        if not applicable:
            return text, 0
        merged = self._dedupe_longest(applicable)
        merged.sort(key=lambda s: s.start, reverse=True)
        out = text
        count = 0
        for s in merged:
            out = out[: s.start] + s.replacement + out[s.end :]
            count += 1
        return out, count

    def _candidate_needles(self, norm_text: str) -> list[_PreparedNeedle]:
        if not norm_text:
            return []
        seen: set[str] = set()
        out: list[_PreparedNeedle] = []
        for ch in set(norm_text):
            for pn in self._needles_by_char.get(ch, ()):
                if pn.norm not in seen:
                    seen.add(pn.norm)
                    out.append(pn)
        out.sort(key=lambda p: len(p.norm), reverse=True)
        return out

    def _find_spans_in_original(
        self,
        text: str,
        norm_text: str,
        orig_indices: list[int],
    ) -> list[MatchSpan]:
        result: list[MatchSpan] = []
        for pn in self._candidate_needles(norm_text):
            if pn.norm not in norm_text:
                continue
            idx = 0
            while True:
                pos = norm_text.find(pn.norm, idx)
                if pos < 0:
                    break
                end = pos + len(pn.norm)
                if self._overlaps_whitelist(pos, end):
                    idx = pos + 1
                    continue
                orig_slice = self._norm_index_to_orig(orig_indices, pos, end, text)
                if orig_slice:
                    o_start, o_end, orig = orig_slice
                    result.append(
                        MatchSpan(
                            start=o_start,
                            end=o_end,
                            original=orig,
                            replacement=pn.replacement,
                            entity_type=pn.entity_type,
                            source=pn.source,
                        )
                    )
                idx = pos + 1
        return result

    @staticmethod
    def _norm_index_to_orig(
        orig_indices: list[int],
        n_start: int,
        n_end: int,
        text: str,
    ) -> tuple[int, int, str] | None:
        if n_end > len(orig_indices):
            return None
        o_start = orig_indices[n_start]
        o_end = orig_indices[n_end - 1] + 1
        return o_start, o_end, text[o_start:o_end]

    def _overlaps_whitelist(self, start: int, end: int) -> bool:
        for ws, we in self.whitelist_protected:
            if start < we and end > ws:
                return True
        return False

    @staticmethod
    def _dedupe_longest(spans: list[MatchSpan]) -> list[MatchSpan]:
        if not spans:
            return []
        spans = sorted(spans, key=lambda s: (-(s.end - s.start), s.start))
        kept: list[MatchSpan] = []
        for s in spans:
            if any(s.start < k.end and s.end > k.start for k in kept):
                continue
            kept.append(s)
        return sorted(kept, key=lambda s: s.start)


def build_replacement_plan(
    *,
    alias_entries: list[tuple[str, str, str, str]],  # alias, placeholder, entity_type, source
    pattern_rules: list[tuple[str, str, str, str]],  # regex, placeholder_prefix, entity_type, source
    whitelist_terms: list[tuple[str, str]],  # term, term_type
    text_for_whitelist: str = "",
) -> ReplacementPlan:
    """Construct plan with length-descending alias matching."""
    plan = ReplacementPlan()
    norm_sample = normalize_for_match(text_for_whitelist) if text_for_whitelist else ""
    for term, ttype in whitelist_terms:
        if ttype == "regex":
            for m in re.finditer(term, text_for_whitelist):
                plan.whitelist_protected.append((m.start(), m.end()))
        else:
            nt = normalize_for_match(term)
            idx = 0
            while norm_sample and nt:
                pos = norm_sample.find(nt, idx)
                if pos < 0:
                    break
                plan.whitelist_protected.append((pos, pos + len(nt)))
                idx = pos + 1

    counters: dict[str, int] = {}
    spans: list[MatchSpan] = []

    def _next_placeholder(prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"[{prefix}_{counters[prefix]}]"

    sorted_aliases = sorted(alias_entries, key=lambda x: len(normalize_for_match(x[0])), reverse=True)
    for alias, placeholder, etype, source in sorted_aliases:
        if not alias.strip():
            continue
        ph = placeholder or _next_placeholder("实体")
        spans.append(MatchSpan(0, 0, alias, ph, etype, source))
        plan.placeholder_map[alias] = ph

    for regex_pat, prefix, etype, source in sorted(pattern_rules, key=lambda x: x[2], reverse=True):
        try:
            for m in re.finditer(regex_pat, text_for_whitelist or ""):
                ph = _next_placeholder(prefix)
                spans.append(MatchSpan(m.start(), m.end(), m.group(), ph, etype, source))
        except re.error:
            continue

    plan.spans = spans
    plan.finalize()
    return plan


def build_plan_from_job_entities(
    entities: list[dict],
    pattern_rules: list[dict],
    whitelist: list[dict],
    sample_text: str = "",
) -> ReplacementPlan:
    """Build plan from confirmed job entity rows."""
    aliases: list[tuple[str, str, str, str]] = []
    for ent in entities:
        if ent.get("is_excluded"):
            continue
        ph = ent.get("placeholder") or "[实体_1]"
        for alias in ent.get("aliases", []):
            aliases.append((alias, ph, ent.get("entity_type", "company"), ent.get("source", "preset")))
    patterns = [
        (r["regex_pattern"], r["placeholder_prefix"], r["entity_type"], "pattern")
        for r in pattern_rules
        if r.get("is_active", True)
    ]
    wl = [(w["term"], w.get("term_type", "exact")) for w in whitelist if w.get("is_active", True)]
    return build_replacement_plan(
        alias_entries=aliases,
        pattern_rules=patterns,
        whitelist_terms=wl,
        text_for_whitelist=sample_text,
    )
