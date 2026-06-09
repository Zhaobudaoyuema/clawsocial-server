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
from app.deid.engine.xml.walker import target_xml_files
from app.deid.office_io import pack_docx, unpack_docx

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

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
    plan = build_plan_from_job_entities(entities, pattern_rules, whitelist, sample_text)

    if force_docx:
        return _run_fallback(input_path, output_path, plan, entities)

    work = Path(tempfile.mkdtemp(prefix="deid_work_"))
    try:
        unpack_docx(input_path, work, merge=True)
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
        pack_docx(work, output_path, validate=False)
        verification = residual_scan(output_path, entities)
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
    """Scan output for alias / pattern residuals."""
    aliases: list[str] = []
    for ent in entities:
        if ent.get("is_excluded"):
            continue
        aliases.extend(ent.get("aliases", []))
        if ent.get("canonical_name"):
            aliases.append(ent["canonical_name"])

    alias_residuals: list[dict] = []
    pattern_residuals: list[dict] = []

    work = Path(tempfile.mkdtemp(prefix="deid_scan_"))
    try:
        unpack_docx(docx_path, work, merge=False)
        idx = 0
        for xf in target_xml_files(work):
            tree = ET.parse(xf)
            for p in tree.getroot().iter(f"{{{W_NS}}}p"):
                texts = [t.text or "" for t in p.iter(f"{{{W_NS}}}t")]
                full = "".join(texts)
                if not full:
                    continue
                norm = normalize_for_match(full)
                for alias in aliases:
                    na = normalize_for_match(alias)
                    if na and na in norm:
                        alias_residuals.append({
                            "text": alias,
                            "location": f"{xf.name}#p{idx}",
                            "snippet": full[:80],
                        })
                for m in CREDIT_CODE_RE.finditer(full):
                    pattern_residuals.append({"type": "credit_code", "snippet": m.group()})
                for m in ID_CARD_RE.finditer(full):
                    pattern_residuals.append({"type": "id_card", "snippet": m.group()[:6] + "…"})
                for m in PHONE_RE.finditer(full):
                    pattern_residuals.append({"type": "phone", "snippet": m.group()})
                idx += 1
    finally:
        shutil.rmtree(work, ignore_errors=True)

    passed = len(alias_residuals) == 0 and len(pattern_residuals) == 0
    return {
        "passed": passed,
        "alias_residuals": alias_residuals[:50],
        "pattern_residuals": pattern_residuals[:50],
    }


def extract_sample_text(docx_path: Path, max_chars: int = 50000) -> str:
    work = Path(tempfile.mkdtemp(prefix="deid_sample_"))
    try:
        unpack_docx(docx_path, work, merge=False)
        chunks: list[str] = []
        for xf in target_xml_files(work):
            tree = ET.parse(xf)
            for p in tree.getroot().iter(f"{{{W_NS}}}p"):
                texts = [t.text or "" for t in p.iter(f"{{{W_NS}}}t")]
                chunks.append("".join(texts))
                if sum(len(c) for c in chunks) > max_chars:
                    break
        return "\n".join(chunks)[:max_chars]
    finally:
        shutil.rmtree(work, ignore_errors=True)
