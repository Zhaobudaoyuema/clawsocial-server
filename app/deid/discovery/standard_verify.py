"""Standard post-run verification flows (post_run_verify + export_readiness)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.deid.discovery.flow_parse import parse_leak_lines, parse_readiness_lines
from app.deid.discovery.flows import FlowItem, default_chunk_user_message, flow_items_from_text_chunks, run_worker_flow
from app.deid.discovery.llm import _chunk_text, get_llm_chunk_params
from app.deid.prompts import (
    FLOW_EXPORT_READINESS_KEY,
    FLOW_POST_RUN_VERIFY_KEY,
    JOB_EXTRA_SEPARATOR,
)
from app.deid.settings_store import get_flow_prompt


def _worker_available(router) -> bool:
    if not router or not router.session:
        return False
    return router.session.state == "ready"


def _format_residuals_ui(verification: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for ar in verification.get("alias_residuals") or []:
        snippet = ar.get("snippet") or ar.get("text") or ""
        lines.append(f"实体残留: {snippet}")
    for pr in verification.get("pattern_residuals") or []:
        lines.append(f"PII ({pr.get('type', '?')}): {pr.get('snippet', '')}")
    for wf in verification.get("worker_findings") or []:
        cat = wf.get("category") or "leak"
        lines.append(f"{cat}: {wf.get('snippet', '')}")
    for mr in verification.get("metadata_residuals") or []:
        lines.append(f"元数据 ({mr.get('field', '?')}): {mr.get('value', '')}")
    return lines[:50]


def _build_summary(verification: dict[str, Any]) -> str:
    readiness = verification.get("readiness") or {}
    if readiness.get("ready") is True:
        level = readiness.get("level") or "standard"
        return f"可外发（{level}）"
    if readiness.get("ready") is False:
        blockers = readiness.get("blockers") or []
        if blockers:
            return f"未通过：{blockers[0]}"
        return "验证未通过"
    if readiness.get("ready") is None:
        notes = readiness.get("notes") or []
        if notes:
            return str(notes[0])
        return "程序验漏通过，建议人工审阅后外发"
    if verification.get("passed"):
        return "程序验漏通过，建议人工审阅后外发"
    return "存在残留，请确认后下载"


def _apply_semantic_readiness(
    readiness: dict,
    semantic_block: dict[str, Any] | None,
) -> dict:
    """Augment readiness from semantic apply results."""
    out = dict(readiness)
    blockers = list(out.get("blockers") or [])
    notes = list(out.get("notes") or [])
    if not semantic_block:
        return out
    missed = int(semantic_block.get("missed_count") or 0)
    applied = int(semantic_block.get("applied_count") or 0)
    scanned = bool(semantic_block.get("scanned"))
    if missed > 0:
        blockers.append(f"语义改写未落地 {missed} 条")
        out["ready"] = False
    if scanned and applied == 0:
        notes.append("已扫描语义指纹但未应用改写")
    missed_samples = semantic_block.get("missed_samples") or []
    from app.deid.discovery.semantic_categories import HIGH_RISK_CATEGORIES, normalize_category

    high_miss = {
        normalize_category(s.get("category"))
        for s in missed_samples
        if normalize_category(s.get("category")) in HIGH_RISK_CATEGORIES
    }
    if high_miss:
        blockers.append("高风险语义指纹未完全改写")
        out["ready"] = False
    out["blockers"] = blockers
    out["notes"] = notes
    if out.get("ready") is not False and scanned and applied > 0 and missed == 0:
        out["level"] = "deep"
        out["identity_safe"] = True
    return out


def merge_verification(
    pipeline_verification: dict[str, Any],
    *,
    worker_available: bool,
    leaks: list[dict] | None = None,
    readiness: dict | None = None,
    flow_summary: dict | None = None,
    deep_completed: bool = False,
    semantic_block: dict[str, Any] | None = None,
    finish_verify_mode: str | None = None,
) -> dict[str, Any]:
    """Build extended verification_json per spec §7."""
    leaks = leaks or []
    readiness = _apply_semantic_readiness(readiness or {}, semantic_block)
    alias_residuals = pipeline_verification.get("alias_residuals") or []
    pattern_residuals = pipeline_verification.get("pattern_residuals") or []
    metadata_clean = pipeline_verification.get("metadata_clean", True)
    confirmed_clean = len(alias_residuals) == 0 and len(pattern_residuals) == 0
    entity_leaks = [lk for lk in leaks if (lk.get("category") or "") == "entity_leak"]
    worker_entity_clean = len(entity_leaks) == 0

    worker_findings = [
        {
            "category": lk.get("category"),
            "snippet": lk.get("snippet"),
            "note": lk.get("note", ""),
        }
        for lk in leaks
    ]

    semantic_skipped = not bool((semantic_block or {}).get("scanned"))
    blockers = list(readiness.get("blockers") or [])
    if semantic_skipped and not any("语义扫描" in str(b) for b in blockers):
        blockers.append("未进行语义扫描")
    readiness_ready = readiness.get("ready")
    if readiness_ready is None:
        if deep_completed and confirmed_clean and metadata_clean:
            readiness_ready = True
        elif semantic_skipped or not confirmed_clean or not metadata_clean:
            readiness_ready = False
        else:
            readiness_ready = None

    level = readiness.get("level") or ("deep" if deep_completed else "standard")
    notes = list(readiness.get("notes") or [])
    if finish_verify_mode == "program_only" and not any("仅程序验漏" in str(n) for n in notes):
        notes.insert(0, "完成阶段仅程序验漏，建议人工审阅后外发")
    if semantic_skipped and not any("语义扫描" in str(n) for n in notes):
        notes.append("未进行语义扫描")
    if not worker_available and finish_verify_mode != "program_only" and not notes:
        notes.append("Worker 离线：未完成 AI 验漏")

    passed = confirmed_clean and metadata_clean and readiness_ready is not False

    out: dict[str, Any] = {
        "passed": passed,
        "worker_available": worker_available,
        "standard": {
            "confirmed_clean": confirmed_clean,
            "metadata_clean": metadata_clean,
            "pattern_pii_clean": len(pattern_residuals) == 0,
            "worker_entity_clean": worker_entity_clean,
        },
        "deep": {
            "completed": deep_completed,
            "identity_safe": readiness.get("identity_safe"),
        },
        "worker_findings": worker_findings,
        "readiness": {
            "ready": readiness_ready,
            "level": level,
            "blockers": blockers,
            "notes": notes,
        },
        "flow_summary": flow_summary or {},
        "alias_residuals": alias_residuals,
        "pattern_residuals": pattern_residuals,
        "metadata_residuals": pipeline_verification.get("metadata_residuals") or [],
        "finish_verify_mode": finish_verify_mode,
        "summary": _build_summary(
            {
                "passed": passed,
                "worker_available": worker_available,
                "readiness": {
                    "ready": readiness_ready,
                    "level": level,
                    "blockers": readiness.get("blockers"),
                    "notes": notes,
                },
            }
        ),
        "residuals": [],
    }
    if semantic_block:
        out["semantic"] = semantic_block
    out["residuals"] = _format_residuals_ui(out)
    return out


async def run_post_run_verify(
    sample: str,
    router,
    db,
    *,
    job_id: int,
    job_extra: str | None = None,
) -> tuple[list[dict], dict]:
    """Flow 3: chunked leak detection on de-identified text."""
    if not sample or not _worker_available(router):
        return [], {"skipped": "worker_offline"}

    chunk_size, overlap = get_llm_chunk_params()
    chunks = _chunk_text(sample, chunk_size, overlap)
    prompt = get_flow_prompt(db, FLOW_POST_RUN_VERIFY_KEY)
    if job_extra:
        prompt = f"{prompt}{JOB_EXTRA_SEPARATOR}{job_extra.strip()}"

    units = flow_items_from_text_chunks(chunks)

    def parse_chunk(content: str, unit: FlowItem) -> list[dict]:
        return parse_leak_lines(content)

    result = await run_worker_flow(
        "post_run_verify",
        units,
        router,
        job_id=job_id,
        db=db,
        system_prompt=prompt,
        build_user_message=default_chunk_user_message,
        parse_chunk=parse_chunk,
    )
    summary = {
        "chunks": result.chunks,
        "skipped": result.skipped,
        "errors": result.errors,
        "elapsed_ms": result.elapsed_ms,
    }
    return result.items, summary


async def run_export_readiness(
    leaks: list[dict],
    pipeline_verification: dict[str, Any],
    router,
    db,
    *,
    job_id: int,
    worker_available: bool,
) -> tuple[dict, dict]:
    """Flow 4: single-call readiness assessment."""
    if not _worker_available(router):
        return {
            "ready": None,
            "blockers": [],
            "notes": ["Worker 离线：跳过就绪评估"],
            "level": "standard",
        }, {"skipped": "worker_offline"}

    leak_summary = [
        {"category": lk.get("category"), "snippet": (lk.get("snippet") or "")[:60], "note": lk.get("note", "")}
        for lk in leaks[:20]
    ]
    meta_residuals = pipeline_verification.get("metadata_residuals") or []
    payload = {
        "worker_available": worker_available,
        "confirmed_clean": len(pipeline_verification.get("alias_residuals") or []) == 0,
        "metadata_clean": pipeline_verification.get("metadata_clean", True),
        "metadata_residuals": meta_residuals[:10],
        "leaks": leak_summary,
        "leak_count": len(leaks),
    }
    user_msg = json.dumps(payload, ensure_ascii=False)[:1500]
    prompt = get_flow_prompt(db, FLOW_EXPORT_READINESS_KEY)

    units = [FlowItem(text=user_msg)]

    def parse_chunk(content: str, unit: FlowItem) -> list[dict]:
        return [parse_readiness_lines(content)]

    result = await run_worker_flow(
        "export_readiness",
        units,
        router,
        job_id=job_id,
        db=db,
        system_prompt=prompt,
        build_user_message=lambda u, i, t: u.text,
        parse_chunk=parse_chunk,
    )
    readiness = result.items[0] if result.items else {}
    readiness.setdefault("level", "standard")
    summary = {
        "skipped": result.skipped,
        "errors": result.errors,
        "elapsed_ms": result.elapsed_ms,
    }
    return readiness, summary


async def run_standard_verify(
    output_path: Path,
    pipeline_verification: dict[str, Any],
    router,
    db,
    *,
    job_id: int,
    job_extra: str | None = None,
    deep_completed: bool = False,
    semantic_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Flow 3+4 and merge into verification_json."""
    from app.deid.engine.pipeline import extract_sample_text

    worker_available = _worker_available(router)
    sample = extract_sample_text(output_path)[:50000] if output_path.exists() else ""

    leaks: list[dict] = []
    flow_summary: dict[str, Any] = {}

    if worker_available and sample:
        leaks, verify_summary = await run_post_run_verify(
            sample, router, db, job_id=job_id, job_extra=job_extra
        )
        flow_summary["post_run_verify"] = verify_summary
        readiness, ready_summary = await run_export_readiness(
            leaks, pipeline_verification, router, db, job_id=job_id, worker_available=worker_available
        )
        flow_summary["export_readiness"] = ready_summary
    else:
        readiness = {
            "ready": None,
            "blockers": [],
            "notes": ["Worker 离线：跳过 AI 验漏"],
            "level": "standard",
        }

    return merge_verification(
        pipeline_verification,
        worker_available=worker_available,
        leaks=leaks,
        readiness=readiness,
        flow_summary=flow_summary,
        deep_completed=deep_completed,
        semantic_block=semantic_block,
    )
