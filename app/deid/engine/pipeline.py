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
from app.deid.engine.plan import ReplacementPlan, build_plan_from_job_entities, normalize_for_match
from app.deid.engine.xml import replace as xml_replace
from app.deid.engine.xml.ns import iter_w
from app.deid.engine.xml.walker import target_xml_files
from app.deid.office_io import pack_docx, unpack_docx

CREDIT_CODE_RE = re.compile(r"\b[0-9A-Z]{18}\b")
ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")


def run_deid_pipeline(
    input_path: Path,
    output_path: Path,
    entities: list[dict],
    pattern_rules: list[dict],
    whitelist: list[dict],
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
        verification = _residual_scan_workdir(work, entities)
        pack_docx(work, output_path, validate=False, fast=fast_io)
        return {
            "engine": "standard",
            "replacement_count": total_repl,
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
