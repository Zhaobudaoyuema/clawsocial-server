"""Markdown de-identification pipeline: read, replace, write."""
from __future__ import annotations

import re
from pathlib import Path

from app.deid.engine.plan import MatchSpan, ReplacementPlan, build_plan_from_job_entities, normalize_for_match

CREDIT_CODE_RE = re.compile(r"\b[0-9A-Z]{18}\b")
ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
_PLACEHOLDER_RE = re.compile(r"\[(?:公司|姓名|机构|实体|人物)_\d+\]")


def _semantic_plan_for_pairs(pairs: list[dict]) -> ReplacementPlan | None:
    spans = [
        MatchSpan(
            start=0,
            end=0,
            original=p["original"],
            replacement=p["rewritten"],
            entity_type="semantic",
            source="semantic",
        )
        for p in pairs
        if p.get("original") and p.get("rewritten") and p["original"] != p["rewritten"]
    ]
    if not spans:
        return None
    plan = ReplacementPlan(spans=spans)
    plan.finalize()
    return plan


def _pair_hits_in_text(plan: ReplacementPlan, text: str) -> bool:
    if not text.strip():
        return False
    _, cnt = plan.apply_to_text(text)
    return cnt > 0


def partition_semantic_pairs_text(
    text: str, pairs: list[dict]
) -> tuple[list[dict], list[dict]]:
    applicable: list[dict] = []
    missed: list[dict] = []
    for pair in pairs:
        plan = _semantic_plan_for_pairs([pair])
        if not plan:
            continue
        if _pair_hits_in_text(plan, text):
            applicable.append(pair)
        else:
            missed.append(pair)
    return applicable, missed


def _count_markdown_tables(text: str) -> int:
    lines = text.splitlines()
    count = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line.startswith("|") and "---" in next_line:
                count += 1
    return count


def extract_md_sample_and_stats(path: Path, max_chars: int = 50000) -> tuple[str, dict]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    non_empty = sum(1 for ln in lines if ln.strip())
    text = raw[:max_chars]
    return text, {
        "paragraph_count": non_empty,
        "char_count": len(raw),
        "table_count": _count_markdown_tables(raw),
        "line_count": len(lines),
    }


def extract_sample_text(path: Path, max_chars: int = 50000) -> str:
    text, _ = extract_md_sample_and_stats(path, max_chars)
    return text


def _norm_line_for_residual(line: str) -> str:
    """Normalize line text with placeholder spans removed (avoid false positives)."""
    stripped = _PLACEHOLDER_RE.sub("", line)
    return normalize_for_match(stripped)


def residual_scan_text(text: str, entities: list[dict]) -> dict:
    """Scan plain text for entity alias / PII residuals."""
    aliases: list[str] = []
    for ent in entities:
        if ent.get("is_excluded"):
            continue
        aliases.extend(ent.get("aliases", []))
        if ent.get("canonical_name"):
            aliases.append(ent["canonical_name"])

    norm_aliases: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        na = normalize_for_match(alias)
        if na and na not in seen:
            seen.add(na)
            norm_aliases.append(na)
    norm_aliases.sort(key=len, reverse=True)

    alias_buckets: dict[str, list[str]] = {}
    for na in norm_aliases:
        alias_buckets.setdefault(na[0], []).append(na)
    for ch in alias_buckets:
        alias_buckets[ch].sort(key=len, reverse=True)

    alias_residuals: list[dict] = []
    pattern_residuals: list[dict] = []

    for idx, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        norm = _norm_line_for_residual(line)
        if norm:
            candidates: list[str] = []
            for ch in set(norm):
                candidates.extend(alias_buckets.get(ch, ()))
            seen_na: set[str] = set()
            for na in sorted(candidates, key=len, reverse=True):
                if na in seen_na:
                    continue
                if na in norm:
                    alias_residuals.append({
                        "text": na,
                        "location": f"line{idx + 1}",
                        "snippet": line[:120],
                    })
                    seen_na.add(na)
                    break
        for m in CREDIT_CODE_RE.finditer(line):
            pattern_residuals.append({"type": "credit_code", "snippet": m.group()})
        for m in ID_CARD_RE.finditer(line):
            pattern_residuals.append({"type": "id_card", "snippet": m.group()[:6] + "…"})
        for m in PHONE_RE.finditer(line):
            pattern_residuals.append({"type": "phone", "snippet": m.group()})
        if len(alias_residuals) >= 50 and len(pattern_residuals) >= 50:
            break

    passed = len(alias_residuals) == 0 and len(pattern_residuals) == 0
    return {
        "passed": passed,
        "alias_residuals": alias_residuals[:50],
        "pattern_residuals": pattern_residuals[:50],
        "metadata_clean": True,
    }


def residual_scan_md(path: Path, entities: list[dict]) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return residual_scan_text(text, entities)


def run_markdown_pipeline(
    input_path: Path,
    output_path: Path,
    entities: list[dict],
    pattern_rules: list[dict],
    whitelist: list[dict],
    semantic_pairs: list[dict] | None = None,
) -> dict:
    sample = input_path.read_text(encoding="utf-8", errors="replace")
    plan = build_plan_from_job_entities(entities, pattern_rules, whitelist, sample)

    total_repl = 0
    lines_out: list[str] = []
    for line in sample.split("\n"):
        new_line, cnt = plan.apply_to_text(line)
        total_repl += cnt
        lines_out.append(new_line)
    result_text = "\n".join(lines_out)

    semantic_applied = 0
    semantic_missed_count = 0
    semantic_missed_samples: list[dict] = []
    applicable_pairs: list[dict] = []

    if semantic_pairs:
        applicable_pairs, missed_pairs = partition_semantic_pairs_text(sample, semantic_pairs)
        semantic_missed_count = len(missed_pairs)
        semantic_missed_samples = [
            {
                "original": (p.get("original") or "")[:80],
                "rewritten": (p.get("rewritten") or "")[:80],
                "category": p.get("category"),
            }
            for p in missed_pairs[:10]
        ]
        if applicable_pairs:
            sem_plan = _semantic_plan_for_pairs(applicable_pairs)
            if sem_plan:
                new_lines: list[str] = []
                for line in result_text.split("\n"):
                    new_line, cnt = sem_plan.apply_to_text(line)
                    semantic_applied += cnt
                    new_lines.append(new_line)
                result_text = "\n".join(new_lines)
                total_repl += semantic_applied

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result_text, encoding="utf-8")

    verification = residual_scan_md(output_path, entities)
    line_count = len(result_text.splitlines())

    return {
        "engine": "markdown",
        "replacement_count": total_repl,
        "semantic_applied_count": semantic_applied,
        "semantic_missed_count": semantic_missed_count,
        "semantic_missed_samples": semantic_missed_samples,
        "semantic_selected_count": len(semantic_pairs or []),
        "coverage": {"lines": line_count},
        "verification": verification,
        "warning": None,
    }
