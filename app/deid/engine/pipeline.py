"""Orchestrate Engine A (XML) then B (fallback); residual scan."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from app.deid.engine.docx_fallback import run_docx_fallback
from app.deid.engine.plan import MatchSpan, ReplacementPlan, build_plan_from_job_entities, normalize_for_match
from app.deid.engine.xml import replace as xml_replace
from app.deid.engine.xml.ns import iter_w
from app.deid.engine.xml.walker import target_xml_files
from app.deid.engine.metadata import scan_metadata_residuals, scrub_docprops
from app.deid.office_io import pack_docx, unpack_docx

CREDIT_CODE_RE = re.compile(r"\b[0-9A-Z]{18}\b")
ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")


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


def _text_from_element(el) -> str:
    return "".join(t.text or "" for t in iter_w(el, "t"))


def _pair_hits_in_text(plan, text: str) -> bool:
    if not text.strip():
        return False
    _, cnt = plan.apply_to_text(text)
    return cnt > 0


def _pair_hits_in_workdir(work: Path, pair: dict) -> bool:
    plan = _semantic_plan_for_pairs([pair])
    if not plan:
        return False
    for xf in target_xml_files(work):
        tree = ET.parse(xf)
        root = tree.getroot()
        for p in iter_w(root, "p"):
            full = _text_from_element(p)
            if _pair_hits_in_text(plan, full):
                return True
        for tc in iter_w(root, "tc"):
            full = _text_from_element(tc)
            if _pair_hits_in_text(plan, full):
                return True
    return False


def partition_semantic_pairs(
    work: Path, pairs: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Split pairs into those that match at least one paragraph vs missed."""
    applicable: list[dict] = []
    missed: list[dict] = []
    for pair in pairs:
        if pair.get("original") and pair.get("rewritten") and pair["original"] != pair["rewritten"]:
            if _pair_hits_in_workdir(work, pair):
                applicable.append(pair)
            else:
                missed.append(pair)
    return applicable, missed


def _apply_semantic_pairs_in_workdir(work: Path, pairs: list[dict]) -> int:
    plan = _semantic_plan_for_pairs(pairs)
    if not plan:
        return 0
    total = 0
    for xf in target_xml_files(work):
        _, cnt = xml_replace.process_xml_file(xf, plan)
        total += cnt
    return total


def run_deid_pipeline(
    input_path: Path,
    output_path: Path,
    entities: list[dict],
    pattern_rules: list[dict],
    whitelist: list[dict],
    semantic_pairs: list[dict] | None = None,
) -> dict:
    """
    Run de-identification. Returns summary dict with engine, counts, verification.
    """
    sample_text = ""
    force_docx = os.getenv("DEID_FORCE_DOCX", "").strip() in ("1", "true")
    fast_io = os.getenv("DEID_FAST_IO", "1").strip().lower() not in ("0", "false", "off")
    plan = build_plan_from_job_entities(entities, pattern_rules, whitelist, sample_text)

    if force_docx:
        return _run_fallback(input_path, output_path, plan, entities)

    work = Path(tempfile.mkdtemp(prefix="deid_work_"))
    try:
        unpack_docx(input_path, work, merge=False, fast=fast_io)
        coverage = {"document": 0, "header": 0, "footer": 0, "footnote": 0, "textbox": 0}
        total_repl = 0
        for xf in target_xml_files(work):
            touched, cnt = xml_replace.process_xml_file(xf, plan)
            total_repl += cnt
            part = xf.name
            if part.startswith("header"):
                coverage["header"] += touched
            elif part.startswith("footer"):
                coverage["footer"] += touched
            elif "footnote" in part or "endnote" in part:
                coverage["footnote"] += touched
            else:
                coverage["document"] += touched
        semantic_applied = 0
        semantic_missed_count = 0
        semantic_missed_samples: list[dict] = []
        applicable_pairs: list[dict] = []
        if semantic_pairs:
            applicable_pairs, missed_pairs = partition_semantic_pairs(work, semantic_pairs)
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
                semantic_applied = _apply_semantic_pairs_in_workdir(work, applicable_pairs)
                total_repl += semantic_applied
        scrub_docprops(work)
        verification = _residual_scan_workdir(work, entities)
        meta_residuals = scan_metadata_residuals(work)
        if meta_residuals:
            verification.setdefault("metadata_residuals", meta_residuals)
            verification["metadata_clean"] = False
            if verification.get("passed"):
                verification["passed"] = False
        else:
            verification["metadata_clean"] = True
        pack_docx(work, output_path, validate=False, fast=fast_io)
        return {
            "engine": "standard",
            "replacement_count": total_repl,
            "semantic_applied_count": semantic_applied,
            "semantic_missed_count": semantic_missed_count,
            "semantic_missed_samples": semantic_missed_samples,
            "semantic_selected_count": len(semantic_pairs or []),
            "coverage": coverage,
            "verification": verification,
            "warning": None,
        }
    except Exception as exc:
        try:
            return _run_fallback(input_path, output_path, plan, entities, reason=str(exc))
        except Exception as exc2:
            return {
                "engine": "failed",
                "error": f"{exc}; fallback: {exc2}",
                "verification": {"passed": False, "alias_residuals": [], "pattern_residuals": []},
            }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_fallback(
    input_path: Path,
    output_path: Path,
    plan: ReplacementPlan,
    entities: list[dict],
    reason: str | None = None,
) -> dict:
    total, coverage = run_docx_fallback(input_path, output_path, plan)
    verification = residual_scan(output_path, entities)
    return {
        "engine": "python-docx-fallback",
        "replacement_count": total,
        "coverage": coverage,
        "verification": verification,
        "warning": "兼容模式：版式可能变化" + (f" ({reason})" if reason else ""),
    }


def residual_scan(docx_path: Path, entities: list[dict]) -> dict:
    """Scan output docx for alias / pattern residuals."""
    work = Path(tempfile.mkdtemp(prefix="deid_scan_"))
    try:
        fast_io = os.getenv("DEID_FAST_IO", "1").strip().lower() not in ("0", "false", "off")
        unpack_docx(docx_path, work, merge=False, fast=fast_io)
        return _residual_scan_workdir(work, entities)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _residual_scan_workdir(work: Path, entities: list[dict]) -> dict:
    """Scan unpacked docx directory for alias / pattern residuals."""
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

    alias_buckets: dict[str, list[str]] = {}
    for na in norm_aliases:
        alias_buckets.setdefault(na[0], []).append(na)

    alias_residuals: list[dict] = []
    pattern_residuals: list[dict] = []

    idx = 0
    for xf in target_xml_files(work):
        tree = ET.parse(xf)
        for p in iter_w(tree.getroot(), "p"):
            texts = [t.text or "" for t in iter_w(p, "t")]
            full = "".join(texts)
            if not full:
                continue
            norm = normalize_for_match(full)
            if norm:
                candidates: list[str] = []
                for ch in set(norm):
                    candidates.extend(alias_buckets.get(ch, ()))
                for na in candidates:
                    if na in norm:
                        alias_residuals.append({
                            "text": na,
                            "location": f"{xf.name}#p{idx}",
                            "snippet": full[:80],
                        })
                        break
            for m in CREDIT_CODE_RE.finditer(full):
                pattern_residuals.append({"type": "credit_code", "snippet": m.group()})
            for m in ID_CARD_RE.finditer(full):
                pattern_residuals.append({"type": "id_card", "snippet": m.group()[:6] + "…"})
            for m in PHONE_RE.finditer(full):
                pattern_residuals.append({"type": "phone", "snippet": m.group()})
            idx += 1
            if len(alias_residuals) >= 50 and len(pattern_residuals) >= 50:
                break
        if len(alias_residuals) >= 50 and len(pattern_residuals) >= 50:
            break

    passed = len(alias_residuals) == 0 and len(pattern_residuals) == 0
    return {
        "passed": passed,
        "alias_residuals": alias_residuals[:50],
        "pattern_residuals": pattern_residuals[:50],
    }


def extract_doc_sample_and_stats(docx_path: Path, max_chars: int = 50000) -> tuple[str, dict]:
    """Extract sample text and document statistics in a single unpack pass."""
    work = Path(tempfile.mkdtemp(prefix="deid_sample_"))
    try:
        fast_io = os.getenv("DEID_FAST_IO", "1").strip().lower() not in ("0", "false", "off")
        unpack_docx(docx_path, work, merge=False, fast=fast_io)
        chunks: list[str] = []
        paragraph_count = 0
        table_count = 0
        char_count = 0
        for xf in target_xml_files(work):
            tree = ET.parse(xf)
            root = tree.getroot()
            table_count += sum(1 for _ in iter_w(root, "tbl"))
            for p in iter_w(root, "p"):
                texts = [t.text or "" for t in iter_w(p, "t")]
                full = "".join(texts)
                if full.strip():
                    paragraph_count += 1
                char_count += len(full)
                chunks.append(full)
                if sum(len(c) for c in chunks) > max_chars:
                    break
        text = "\n".join(chunks)[:max_chars]
        return text, {
            "paragraph_count": paragraph_count,
            "char_count": char_count,
            "table_count": table_count,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def extract_sample_text(docx_path: Path, max_chars: int = 50000) -> str:
    text, _ = extract_doc_sample_and_stats(docx_path, max_chars)
    return text
