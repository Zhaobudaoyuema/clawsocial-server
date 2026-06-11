"""Program scan: dry-run replace, residual detect, C3 auto-fix before confirm."""
from __future__ import annotations

import re
import uuid
from typing import Any

from app.deid.discovery.entity_leak import _ORG_HINT
from app.deid.discovery.enrich import _chars_subsequence
from app.deid.engine.markdown_pipeline import _PLACEHOLDER_RE, residual_scan_text
from app.deid.engine.plan import normalize_for_match
from app.deid.engine.preview import build_preview_text

_MIN_SPAN_LEN = 4
_ORG_SPAN_RE = re.compile(
    r"[\u4e00-\u9fff0-9（）()A-Za-z·\-]+"
    r"(?:集团[\u4e00-\u9fff0-9（）()A-Za-z·\-]*)?"
    r"(?:股份有限公司|有限责任公司|有限公司|事务所|有限合伙|设计院|中心)"
)
_ORG_GROUP_RE = re.compile(
    r"[\u4e00-\u9fff0-9（）()A-Za-z·\-]{2,40}集团"
)


def _entity_names(ent: dict) -> list[str]:
    names: list[str] = []
    c = (ent.get("canonical_name") or "").strip()
    if c:
        names.append(c)
    for a in ent.get("aliases") or []:
        s = (a or "").strip()
        if s and s not in names:
            names.append(s)
    return names


def _known_norms(entities: list[dict]) -> set[str]:
    out: set[str] = set()
    for ent in entities:
        if ent.get("is_excluded"):
            continue
        for n in _entity_names(ent):
            na = normalize_for_match(n)
            if na:
                out.add(na)
    return out


def _org_candidates_from_line(line: str) -> list[str]:
    if not line.strip():
        return []
    out: list[str] = []
    seen: set[str] = set()
    for pattern in (_ORG_SPAN_RE, _ORG_GROUP_RE):
        for m in pattern.finditer(line):
            s = m.group(0).strip()
            ns = normalize_for_match(s)
            if len(ns) >= _MIN_SPAN_LEN and ns not in seen:
                seen.add(ns)
                out.append(s)
    if out:
        out.sort(key=lambda x: len(normalize_for_match(x)), reverse=True)
        filtered: list[str] = []
        norms: list[str] = []
        for s in out:
            ns = normalize_for_match(s)
            if any(ns != ln and ns in ln for ln in norms):
                continue
            filtered.append(s)
            norms.append(ns)
        return filtered
    parts = re.split(r"[|，,；;]", line)
    if len(parts) <= 1:
        parts = [line]
    for part in parts:
        s = part.strip()
        if len(s) < _MIN_SPAN_LEN:
            continue
        if _PLACEHOLDER_RE.fullmatch(s):
            continue
        if _PLACEHOLDER_RE.search(s) and len(s) <= 40:
            continue
        ns = normalize_for_match(s)
        if ns in seen:
            continue
        if _ORG_HINT.search(s):
            seen.add(ns)
            out.append(s)
    out.sort(key=lambda x: len(normalize_for_match(x)), reverse=True)
    return out


def _locate_source_span(source_line: str, residual: dict) -> str | None:
    needle = normalize_for_match(str(residual.get("text") or ""))
    if not needle:
        return None
    for cand in _org_candidates_from_line(source_line):
        nc = normalize_for_match(cand)
        if needle in nc or nc in needle:
            return cand
    norm_line = normalize_for_match(_PLACEHOLDER_RE.sub("", source_line))
    if needle and needle in norm_line:
        idx = norm_line.find(needle)
        if idx >= 0:
            for cand in _org_candidates_from_line(source_line):
                if needle in normalize_for_match(cand):
                    return cand
    snippet = str(residual.get("snippet") or "")
    if snippet:
        for cand in _org_candidates_from_line(source_line):
            if cand in source_line and cand in snippet:
                return cand
            if normalize_for_match(cand) in normalize_for_match(snippet):
                return cand
    return None


def _c3_overlap_score(nt: str, nn: str) -> int:
    if not nt or not nn:
        return 0
    if nt == nn:
        return max(len(nt), len(nn)) + 100
    if nt in nn or nn in nt:
        return min(len(nt), len(nn)) + 50
    if _chars_subsequence(nn, nt) or _chars_subsequence(nt, nn):
        return min(len(nt), len(nn)) + 20
    prefix = 0
    for a, b in zip(nt, nn):
        if a != b:
            break
        prefix += 1
    if prefix >= _MIN_SPAN_LEN:
        return prefix + 10
    return 0


def _c3_match_entity(text: str, entities: list[dict]) -> dict | None:
    nt = normalize_for_match(text)
    if not nt:
        return None
    best: dict | None = None
    best_score = 0
    for ent in entities:
        if ent.get("is_excluded"):
            continue
        for name in _entity_names(ent):
            nn = normalize_for_match(name)
            if not nn:
                continue
            score = _c3_overlap_score(nt, nn)
            if score > best_score:
                best_score = score
                best = ent
    return best if best_score >= _MIN_SPAN_LEN + 10 else None


def dry_run_preview(
    sample: str,
    entities: list[dict],
    pattern_rules: list[dict],
    whitelist: list[dict],
    *,
    type_prefix_map: dict[str, str],
) -> str:
    return build_preview_text(
        sample, entities, pattern_rules, whitelist, type_prefix_map=type_prefix_map
    )


def count_residuals(preview_text: str, entities: list[dict]) -> dict[str, Any]:
    result = residual_scan_text(preview_text, entities)
    alias_n = len(result.get("alias_residuals") or [])
    pattern_n = len(result.get("pattern_residuals") or [])
    return {
        **result,
        "residual_count": alias_n + pattern_n,
        "alias_count": alias_n,
        "pattern_count": pattern_n,
    }


def _uncovered_org_spans(source: str, preview: str, entities: list[dict]) -> list[str]:
    """Org-like spans in source that still appear literally in dry-run preview."""
    known = _known_norms(entities)
    src_lines = source.splitlines()
    prv_lines = preview.splitlines()
    max_len = max(len(src_lines), len(prv_lines))
    found: list[str] = []
    seen: set[str] = set()
    for i in range(max_len):
        sl = src_lines[i] if i < len(src_lines) else ""
        pl = prv_lines[i] if i < len(prv_lines) else ""
        for cand in _org_candidates_from_line(sl):
            ns = normalize_for_match(cand)
            if not ns or ns in known or ns in seen:
                continue
            if cand in pl or normalize_for_match(cand) in normalize_for_match(
                _PLACEHOLDER_RE.sub("", pl)
            ):
                seen.add(ns)
                found.append(cand)
    found.sort(key=lambda x: len(normalize_for_match(x)), reverse=True)
    return found


def plan_fixes(
    source: str,
    preview_text: str,
    entities: list[dict],
    residual: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build deduped fix actions from residual scan + uncovered org spans."""
    source_lines = source.splitlines()
    known = _known_norms(entities)
    planned: list[dict[str, Any]] = []
    seen_text: set[str] = set()

    def _queue_span(span: str) -> None:
        candidates = _org_candidates_from_line(span) or [span.strip()]
        for cand in candidates:
            ns = normalize_for_match(cand)
            if not ns or ns in known or ns in seen_text or len(ns) < _MIN_SPAN_LEN:
                continue
            seen_text.add(ns)
            hit_count = source.count(cand)
            ent = _c3_match_entity(cand, entities)
            if ent:
                planned.append({
                    "action": "add_alias",
                    "text": cand,
                    "entity_id": ent.get("id"),
                    "canonical_name": ent.get("canonical_name"),
                    "hit_count": hit_count,
                })
            else:
                planned.append({
                    "action": "new_entity",
                    "text": cand,
                    "hit_count": hit_count,
                })

    for span in _uncovered_org_spans(source, preview_text, entities):
        _queue_span(span)

    for ar in residual.get("alias_residuals") or []:
        loc = str(ar.get("location") or "")
        m = re.match(r"line(\d+)", loc)
        if not m:
            continue
        line_idx = int(m.group(1)) - 1
        if line_idx < 0 or line_idx >= len(source_lines):
            continue
        span = _locate_source_span(source_lines[line_idx], ar)
        if span:
            _queue_span(span)

    planned.sort(key=lambda x: len(normalize_for_match(x["text"])), reverse=True)
    return planned


def simulate_run(
    source: str,
    entities: list[dict],
    pattern_rules: list[dict],
    whitelist: list[dict],
    *,
    type_prefix_map: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    preview = dry_run_preview(
        source, entities, pattern_rules, whitelist, type_prefix_map=type_prefix_map
    )
    before = count_residuals(preview, entities)
    fixes = plan_fixes(source, preview, entities, before)
    return before, fixes


def new_change_id() -> str:
    return uuid.uuid4().hex[:12]
