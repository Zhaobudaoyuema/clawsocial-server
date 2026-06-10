"""De-identification job state machine and library operations."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.deid.discovery.entity_leak import run_entity_leak_scan
from app.deid.discovery.entity_rescan import (
    diff_canonical_vs_initial,
    run_initial_scan,
    run_re_scan,
    snapshot_entities,
)
from app.deid.discovery.experience_store import (
    append_global_experience,
    delete_global_experience,
    list_global_experience,
    list_global_experience_texts,
    update_global_experience,
)
from app.deid.discovery.scan_experience import run_scan_experience
from app.deid.discovery.semantic_categories import HIGH_RISK_CATEGORIES, normalize_category
from app.deid.discovery.standard_verify import merge_verification
from app.deid.discovery.deep_flows import (
    find_risk_by_id,
    run_deep_detect,
    run_deep_suggest,
    run_deep_suggest_all,
    update_risk_in_list,
)
from app.deid.discovery.llm import build_scan_chunk_plan, count_llm_chunks
from app.deid.discovery.merge import MergedEntity, merge_entities
from app.deid.engine.pipeline import extract_doc_sample_and_stats, extract_sample_text, run_deid_pipeline
from app.deid.engine.plan import normalize_for_match
from app.deid.engine.preview import assign_placeholder_map, build_preview_text
from app.deid.prompts import (
    DEFAULT_SCAN_PROMPT,
    FLOW_RE_DISCOVER_KEY,
    SCAN_PROMPT_SETTING_KEY,
    build_scan_system_prompt,
)
from app.deid.settings_store import get_flow_prompt
from app.deid.entity_types import get_placeholder_prefix, list_entity_types, valid_codes
from app.deid.schemas import ManualEntityIn
from app.deid.scan_events import get_scan_event_bus
from app.deid.settings_store import (
    get_export_filename_mode,
    get_scan_prompt,
    reset_scan_prompt,
    scan_prompt_meta,
    set_setting,
)
from app.deid.rehydrate import build_placeholder_map, rehydrate_text
from app.deid.storage import (
    JOB_RETENTION_HOURS,
    MAPPING_RETENTION_DAYS,
    delete_job_files,
    job_dir,
    resolve_upload_path,
    save_job_docx,
)
from app.deid.worker.router import WorkerRouter
from app.models_deid import (
    DeidClientPack,
    DeidEntity,
    DeidEntityAlias,
    DeidEntityMapping,
    DeidGlobalExperience,
    DeidJob,
    DeidJobEntity,
    DeidJobEntityAlias,
    DeidPatternRule,
    DeidWhitelistTerm,
)
from app.time_utils import coerce_beijing, now_beijing

SOURCE_UI = {
    "manual": "手动",
    "llm": "AI 识别",
    "remembered": "已记住",
}

_AUTO_SOURCES = frozenset({"llm", "remembered", "leak_verify"})
_CONF_ALIAS_PREFIX = "__conf:"


def _merged_entities_snapshot(entities: list[MergedEntity]) -> list[dict]:
    return [
        {
            "canonical_name": e.canonical_name,
            "entity_type": e.entity_type,
            "source": e.source,
            "aliases": e.aliases,
            "hit_count": e.hit_count,
        }
        for e in entities
    ]


def _load_global_experience_lines(db: Session) -> list[str]:
    return list_global_experience_texts(db, limit=10)


def _parse_initial_snapshot(job: DeidJob) -> list[dict]:
    try:
        raw = json.loads(job.initial_entities_snapshot_json or "[]")
        return raw if isinstance(raw, list) else []
    except json.JSONDecodeError:
        return []


def _delta_vs_initial_count(job: DeidJob, entities: list[MergedEntity]) -> int:
    initial = _parse_initial_snapshot(job)
    if not initial:
        return 0
    return len(diff_canonical_vs_initial(initial, entities))


def _parse_pack_ids(job: DeidJob) -> list[int]:
    try:
        return json.loads(job.pack_ids_json or "[]")
    except json.JSONDecodeError:
        return []


def _dt_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    c = coerce_beijing(dt)
    return c.isoformat() if c else None


def _parse_progress(job: DeidJob) -> dict[str, Any] | None:
    if not job.progress_json:
        return None
    try:
        return json.loads(job.progress_json)
    except json.JSONDecodeError:
        return None


def _job_scan_chunk_plan(job: DeidJob) -> dict | None:
    progress = _parse_progress(job) or {}
    stats = progress.get("stats") or {}
    plan = stats.get("scan_chunk_plan")
    return plan if isinstance(plan, dict) else None


_LOG_TAIL_MAX = 30


def _merge_progress_payload(
    job: DeidJob,
    *,
    phase: str,
    percent: int,
    message: str,
    queue_position: int | None = None,
    stats: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    log_line: str | None = None,
    wizard_step: str | None = None,
) -> dict[str, Any]:
    prev = _parse_progress(job) or {}
    log_tail = list(prev.get("log_tail") or [])
    if log_line:
        log_tail.append(log_line)
        if len(log_tail) > _LOG_TAIL_MAX:
            log_tail = log_tail[-_LOG_TAIL_MAX:]
    payload: dict[str, Any] = {
        "phase": phase,
        "percent": max(0, min(100, percent)),
        "message": message,
    }
    if queue_position is not None:
        payload["queue_position"] = queue_position
    if stats is not None:
        payload["stats"] = stats
    elif prev.get("stats"):
        payload["stats"] = prev["stats"]
    if metrics is not None:
        payload["metrics"] = metrics
    elif prev.get("metrics"):
        payload["metrics"] = prev["metrics"]
    if log_tail:
        payload["log_tail"] = log_tail
    if wizard_step is not None:
        payload["wizard_step"] = wizard_step
    elif prev.get("wizard_step"):
        payload["wizard_step"] = prev["wizard_step"]
    return payload


def set_job_progress(
    db: Session,
    job: DeidJob,
    *,
    phase: str,
    percent: int,
    message: str,
    queue_position: int | None = None,
    stats: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    log_line: str | None = None,
    wizard_step: str | None = None,
    commit: bool = True,
    emit: bool = True,
) -> None:
    payload = _merge_progress_payload(
        job,
        phase=phase,
        percent=percent,
        message=message,
        queue_position=queue_position,
        stats=stats,
        metrics=metrics,
        log_line=log_line,
        wizard_step=wizard_step,
    )
    job.progress_json = json.dumps(payload, ensure_ascii=False)
    if commit:
        db.commit()
    if emit:
        bus = get_scan_event_bus()
        bus.emit(
            job.id,
            {
                "type": "phase",
                "phase": phase,
                "percent": payload["percent"],
                "message": message,
            },
        )
        if stats:
            bus.emit(job.id, {"type": "stats", **stats})
        if metrics:
            bus.emit(job.id, {"type": "metrics", **metrics})
        if log_line:
            bus.emit(job.id, {"type": "log", "line": log_line})


def job_needs_worker_queue(
    db: Session,
    job: DeidJob,
    worker_router: WorkerRouter | None,
) -> bool:
    """True when this job should enter the FIFO worker queue."""
    if not job.use_worker:
        return False
    import os

    enabled = os.getenv("DEID_LLM_ENABLED", "1").strip().lower() not in ("0", "false", "off")
    if not enabled:
        return False
    if not worker_router or not worker_router.session:
        return False
    return True


def get_job(db: Session, job_id: int) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    out = _job_to_dict(job, db)
    out["progress"] = _parse_progress(job)
    out["use_worker"] = job.use_worker
    return out


def _mapping_count(db: Session, job_id: int) -> int:
    return (
        db.query(DeidEntityMapping)
        .filter(DeidEntityMapping.job_id == job_id)
        .count()
    )


def _ensure_job_mappings(db: Session, job_id: int) -> None:
    """Backfill mapping rows from job_entities for jobs completed before rehydrate shipped."""
    if _mapping_count(db, job_id) > 0:
        return
    job = db.get(DeidJob, job_id)
    if not job or job.status not in ("done", "archived"):
        return
    entities = [
        e
        for e in list_job_entities(db, job_id)
        if not e.get("is_excluded") and e.get("placeholder")
    ]
    if not entities:
        return
    _write_mappings(db, job_id, entities)
    db.commit()


def _job_rehydrate_meta(db: Session, job: DeidJob) -> dict[str, Any]:
    completed_at = coerce_beijing(job.completed_at)
    mapping_expires_at = None
    rehydrate_available = False
    if completed_at and job.status in ("done", "archived"):
        _ensure_job_mappings(db, job.id)
        mapping_expires_at = completed_at + timedelta(days=MAPPING_RETENTION_DAYS)
        rehydrate_available = (
            _mapping_count(db, job.id) > 0 and now_beijing() < mapping_expires_at
        )
    return {
        "files_purged_at": _dt_iso(job.files_purged_at),
        "mapping_expires_at": _dt_iso(mapping_expires_at) if mapping_expires_at else None,
        "rehydrate_available": rehydrate_available,
    }


def _job_to_dict(job: DeidJob, db: Session | None = None) -> dict[str, Any]:
    hours = None
    completed_at = coerce_beijing(job.completed_at)
    expires_at = coerce_beijing(job.expires_at)
    if completed_at and expires_at and job.status == "done":
        delta = expires_at - now_beijing()
        hours = max(0, delta.total_seconds() / 3600)
    verification = None
    if job.verification_json:
        try:
            verification = json.loads(job.verification_json)
        except json.JSONDecodeError:
            pass
    run_summary = None
    if job.run_summary_json:
        try:
            run_summary = json.loads(job.run_summary_json)
        except json.JSONDecodeError:
            pass
    out: dict[str, Any] = {
        "id": job.id,
        "status": job.status,
        "pack_ids": _parse_pack_ids(job),
        "original_filename": job.original_filename,
        "engine": job.engine,
        "verification": verification,
        "run_summary": run_summary,
        "override_reason": job.override_reason,
        "completed_at": _dt_iso(job.completed_at),
        "expires_at": _dt_iso(job.expires_at),
        "created_at": _dt_iso(job.created_at),
        "hours_until_cleanup": hours,
        "use_worker": job.use_worker,
        "semantic_skipped": bool(job.semantic_skipped),
        "re_run_count": job.re_run_count or 0,
        "experience_eligible": bool(job.experience_eligible),
        "initial_entity_count": len(_parse_initial_snapshot(job)),
        "delta_vs_initial_count": _delta_vs_initial_count(
            job, _job_entities_as_merged(db, job.id) if db else []
        )
        if db
        else 0,
        "progress": _parse_progress(job),
        "files_purged_at": None,
        "mapping_expires_at": None,
        "rehydrate_available": False,
    }
    if db is not None:
        out.update(_job_rehydrate_meta(db, job))
        active_ids = {
            r.id
            for r in db.query(DeidJobEntity)
            .filter(DeidJobEntity.job_id == job.id, DeidJobEntity.is_excluded.is_(False))
            .all()
        }
        out["semantic_stale"] = _semantic_entity_stale(job, active_ids)
    return out


def list_jobs(db: Session) -> list[dict]:
    mapping_cutoff = now_beijing() - timedelta(days=MAPPING_RETENTION_DAYS)
    finished_jobs = (
        db.query(DeidJob)
        .filter(
            DeidJob.status.in_(("done", "archived")),
            DeidJob.completed_at.isnot(None),
            DeidJob.completed_at >= mapping_cutoff,
        )
        .order_by(DeidJob.created_at.desc())
        .all()
    )
    incomplete = (
        db.query(DeidJob)
        .filter(~DeidJob.status.in_(("done", "archived")))
        .order_by(DeidJob.created_at.desc())
        .all()
    )
    seen: set[int] = set()
    out: list[dict] = []
    for j in finished_jobs + incomplete:
        if j.id in seen:
            continue
        seen.add(j.id)
        out.append(_job_to_dict(j, db))
    return out


def _storage_pack_id(db: Session) -> int | None:
    pack = (
        db.query(DeidClientPack)
        .filter(DeidClientPack.code == "general_finance", DeidClientPack.is_active.is_(True))
        .first()
    )
    if pack:
        return pack.id
    pack = db.query(DeidClientPack).filter(DeidClientPack.is_active.is_(True)).first()
    return pack.id if pack else None


def _purge_job(db: Session, job_id: int, *, commit: bool = True) -> None:
    job = db.get(DeidJob, job_id)
    if not job:
        return
    db.query(DeidGlobalExperience).filter(DeidGlobalExperience.source_job_id == job_id).update(
        {DeidGlobalExperience.source_job_id: None},
        synchronize_session=False,
    )
    from app.deid.worker_call_store import delete_worker_calls_for_job

    delete_worker_calls_for_job(db, job_id)
    db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).delete()
    db.query(DeidJobEntityAlias).filter(
        DeidJobEntityAlias.job_entity_id.in_(
            db.query(DeidJobEntity.id).filter(DeidJobEntity.job_id == job_id)
        )
    ).delete(synchronize_session=False)
    db.query(DeidJobEntity).filter(DeidJobEntity.job_id == job_id).delete()
    db.delete(job)
    if commit:
        db.commit()
        delete_job_files(job_id)


def purge_incomplete_jobs(db: Session, *, keep_job_id: int | None = None) -> int:
    """Remove all non-done jobs (not shown in history). Returns count removed."""
    q = db.query(DeidJob).filter(~DeidJob.status.in_(("done", "archived")))
    if keep_job_id is not None:
        q = q.filter(DeidJob.id != keep_job_id)
    ids = [j.id for j in q.all()]
    for job_id in ids:
        _purge_job(db, job_id, commit=False)
    if ids:
        db.commit()
        for job_id in ids:
            delete_job_files(job_id)
    return len(ids)


async def create_job(
    db: Session,
    file: UploadFile,
    pack_ids: list[int] | None,
    *,
    prompt_extra: str | None = None,
    use_worker: bool = True,
) -> dict:
    if pack_ids is None:
        storage = _storage_pack_id(db)
        pack_ids = [storage] if storage else []
    extra = (prompt_extra or "").strip() or None
    job = DeidJob(
        status="draft",
        pack_ids_json=json.dumps(pack_ids),
        original_filename=file.filename or "document.docx",
        prompt_extra=extra,
        use_worker=use_worker,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    rel, original = await save_job_docx(job.id, file)
    job.stored_path = rel
    job.original_filename = original
    db.commit()
    return _job_to_dict(job, db)


def _load_library_aliases(db: Session, pack_ids: list[int]) -> list[tuple[DeidEntity, DeidEntityAlias]]:
    q = (
        db.query(DeidEntity, DeidEntityAlias)
        .join(DeidEntityAlias, DeidEntityAlias.entity_id == DeidEntity.id)
        .filter(DeidEntity.pack_id.in_(pack_ids), DeidEntity.is_active.is_(True))
    )
    return q.all()


def _count_hits(text_norm: str, alias: str) -> int:
    na = normalize_for_match(alias)
    if not na:
        return 0
    return text_norm.count(na)


def _add_job_entity_alias(
    db: Session,
    seen_aliases: dict[int, set[str]],
    job_entity_id: int,
    alias_text: str,
) -> None:
    """Insert alias once per job entity (canonical may also appear in alias rows)."""
    if not alias_text or alias_text.startswith(_CONF_ALIAS_PREFIX):
        return
    bucket = seen_aliases.setdefault(job_entity_id, set())
    if alias_text in bucket:
        return
    bucket.add(alias_text)
    db.add(DeidJobEntityAlias(job_entity_id=job_entity_id, alias_text=alias_text))


def _add_confidence_alias(db: Session, job_entity_id: int, confidence: float | None) -> None:
    if confidence is None:
        return
    db.add(
        DeidJobEntityAlias(
            job_entity_id=job_entity_id,
            alias_text=f"{_CONF_ALIAS_PREFIX}{confidence:.2f}",
        )
    )


def _parse_confidence(aliases: list[str]) -> float | None:
    for a in aliases:
        if a.startswith(_CONF_ALIAS_PREFIX):
            try:
                return float(a[len(_CONF_ALIAS_PREFIX) :])
            except ValueError:
                return None
    return None


def _clear_auto_entities(db: Session, job_id: int) -> None:
    auto_ids = [
        e.id
        for e in db.query(DeidJobEntity).filter(
            DeidJobEntity.job_id == job_id,
            DeidJobEntity.source.in_(_AUTO_SOURCES),
        )
    ]
    if auto_ids:
        db.query(DeidJobEntityAlias).filter(
            DeidJobEntityAlias.job_entity_id.in_(auto_ids)
        ).delete(synchronize_session=False)
        db.query(DeidJobEntity).filter(DeidJobEntity.id.in_(auto_ids)).delete(
            synchronize_session=False
        )


def _discover_remembered(
    db: Session,
    text_norm: str,
) -> tuple[list[MergedEntity], int]:
    merged: list[MergedEntity] = []
    hit_total = 0
    seen_keys: set[str] = set()
    rows = (
        db.query(DeidEntity, DeidEntityAlias)
        .join(DeidEntityAlias, DeidEntityAlias.entity_id == DeidEntity.id)
        .filter(DeidEntity.is_active.is_(True))
        .all()
    )
    by_entity: dict[int, tuple[DeidEntity, list[str]]] = {}
    for ent, alias_row in rows:
        bucket = by_entity.setdefault(ent.id, (ent, []))
        if alias_row.alias_text not in bucket[1]:
            bucket[1].append(alias_row.alias_text)

    for ent, aliases in by_entity.values():
        all_texts = list(aliases)
        if ent.canonical_name and ent.canonical_name not in all_texts:
            all_texts.insert(0, ent.canonical_name)
        hits = 0
        for t in all_texts:
            hits = max(hits, _count_hits(text_norm, t))
        if hits == 0:
            continue
        key = normalize_for_match(ent.canonical_name)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        hit_total += hits
        merged.append(
            MergedEntity(
                canonical_name=ent.canonical_name,
                entity_type=ent.entity_type,
                source="remembered",
                aliases=all_texts,
                hit_count=hits,
                library_entity_id=ent.id,
            )
        )
    return merged, hit_total


def _persist_merged_entities(
    db: Session,
    job_id: int,
    entities: list[MergedEntity],
) -> None:
    seen_aliases: dict[int, set[str]] = {}
    for ent in entities:
        je = DeidJobEntity(
            job_id=job_id,
            entity_type=ent.entity_type,
            canonical_name=ent.canonical_name,
            source=ent.source,
            hit_count=ent.hit_count,
            library_entity_id=ent.library_entity_id,
        )
        db.add(je)
        db.flush()
        _add_job_entity_alias(db, seen_aliases, je.id, ent.canonical_name)
        for alias in ent.aliases:
            _add_job_entity_alias(db, seen_aliases, je.id, alias)
        if ent.confidence is not None:
            _add_confidence_alias(db, je.id, ent.confidence)


async def scan_job(
    db: Session,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    """Synchronous scan (tests / legacy). Runs inline without queue."""
    return await _scan_job_impl(db, job_id, worker_router=worker_router, queue=None)


async def scan_job_async(
    db: Session,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
    queue: Any | None = None,
) -> dict:
    """Background scan with progress updates."""
    return await _scan_job_impl(db, job_id, worker_router=worker_router, queue=queue)


async def _scan_job_impl(
    db: Session,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
    queue: Any | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job or not job.stored_path:
        raise HTTPException(404, "任务不存在或未上传文件")
    pack_ids = _parse_pack_ids(job)
    path = resolve_upload_path(job.stored_path)
    if not path.exists():
        raise HTTPException(400, "原文件已丢失")

    _clear_auto_entities(db, job_id)
    if job.status not in ("scanning", "queued"):
        job.status = "scanning"
    bus = get_scan_event_bus()
    set_job_progress(
        db,
        job,
        phase="starting",
        percent=1,
        message="准备扫描…",
        log_line="扫描任务已开始",
        commit=True,
    )

    manual_entities = (
        db.query(DeidJobEntity)
        .filter(DeidJobEntity.job_id == job_id, DeidJobEntity.source == "manual")
        .all()
    )
    manual_merged: list[MergedEntity] = []
    for me in manual_entities:
        aliases = [
            a.alias_text
            for a in db.query(DeidJobEntityAlias).filter(
                DeidJobEntityAlias.job_entity_id == me.id
            )
            if not a.alias_text.startswith(_CONF_ALIAS_PREFIX)
        ]
        manual_merged.append(
            MergedEntity(
                canonical_name=me.canonical_name,
                entity_type=me.entity_type,
                source="manual",
                aliases=aliases or [me.canonical_name],
                hit_count=me.hit_count,
            )
        )

    set_job_progress(
        db,
        job,
        phase="extract",
        percent=5,
        message="提取文档文本…",
        log_line="正在解压并读取文档…",
        commit=True,
    )

    import os

    sample, doc_stats = extract_doc_sample_and_stats(path)
    text_norm = normalize_for_match(sample)
    scan_chunk_plan = build_scan_chunk_plan(sample)
    llm_chunk_count = count_llm_chunks(sample)
    stats_payload = {
        "paragraphs": doc_stats["paragraph_count"],
        "chars": doc_stats["char_count"],
        "tables": doc_stats["table_count"],
        "chunks": llm_chunk_count,
        "scan_chunk_plan": scan_chunk_plan,
    }
    stats_msg = (
        f"已解析 {doc_stats['paragraph_count']:,} 段 · "
        f"{doc_stats['char_count']:,} 字"
    )
    if llm_chunk_count > 1:
        stats_msg += f" · 将分 {llm_chunk_count} 段分析"
    set_job_progress(
        db,
        job,
        phase="extract",
        percent=15,
        message=stats_msg,
        stats=stats_payload,
        log_line=stats_msg,
        commit=True,
    )

    set_job_progress(
        db,
        job,
        phase="remembered",
        percent=20,
        message="匹配已记住实体…",
        stats=stats_payload,
        log_line="匹配词库与已记住实体…",
    )
    remembered_entities, remembered_hits = _discover_remembered(db, text_norm)
    remembered_names = [e.canonical_name for e in remembered_entities[:5]]
    bus.emit(
        job_id,
        {
            "type": "remembered",
            "count": remembered_hits,
            "names": remembered_names,
        },
    )
    set_job_progress(
        db,
        job,
        phase="remembered",
        percent=25,
        message=f"词库匹配 {remembered_hits} 个实体",
        stats=stats_payload,
        log_line=f"词库匹配完成，命中 {remembered_hits} 个实体",
        commit=True,
    )

    llm_enabled = job.use_worker and job_needs_worker_queue(db, job, worker_router)
    base_system_prompt = build_scan_system_prompt(
        get_scan_prompt(db),
        job.prompt_extra,
        entity_types=list_entity_types(db),
    )
    valid_types = frozenset(valid_codes(db))
    base_entities = merge_entities(manual_merged + remembered_entities)

    scan_result = None
    scan_metrics: dict[str, Any] = {"model": None}
    scan_percent = 30

    def on_scan_progress(current: int, total: int, *, phase: str) -> None:
        nonlocal scan_percent
        if total <= 0:
            return
        scan_percent = 30 + int(55 * current / total)
        set_job_progress(
            db,
            job,
            phase=phase,
            percent=scan_percent,
            message=f"初次识别 {current}/{total}",
            stats=stats_payload,
            metrics=scan_metrics if scan_metrics.get("model") else None,
            commit=True,
            emit=False,
        )

    def on_scan_event(event: dict) -> None:
        bus.emit(job_id, event)
        if event.get("type") == "metrics":
            scan_metrics.update(event)

    if llm_enabled and worker_router:
        set_job_progress(
            db,
            job,
            phase="initial_discover",
            percent=30,
            message="初次识别中…",
            stats=stats_payload,
            log_line="启动初次实体识别…",
        )
        exp_lines = _load_global_experience_lines(db)

        def progress_discover(c: int, t: int) -> None:
            on_scan_progress(c, t, phase="initial_discover")

        scan_result = await run_initial_scan(
            sample,
            base_entities,
            worker_router,
            db,
            job_id=job_id,
            system_prompt=base_system_prompt,
            valid_entity_types=valid_types,
            exp_lines=exp_lines,
            on_progress=progress_discover,
            on_event=on_scan_event,
        )
        merged = scan_result.entities
        bus.emit(
            job_id,
            {
                "type": "entities_snapshot",
                "round": "initial",
                "entities": _merged_entities_snapshot(merged),
            },
        )

        set_job_progress(
            db,
            job,
            phase="re_discover_auto",
            percent=75,
            message="自动再识别中…",
            stats=stats_payload,
            log_line="启动自动再识别（补漏简称与别名）…",
        )
        re_prompt = get_flow_prompt(db, FLOW_RE_DISCOVER_KEY)
        if job.prompt_extra:
            from app.deid.prompts import JOB_EXTRA_SEPARATOR

            re_prompt = f"{re_prompt}{JOB_EXTRA_SEPARATOR}{job.prompt_extra.strip()}"

        def progress_auto_rescan(c: int, t: int) -> None:
            on_scan_progress(c, t, phase="re_discover_auto")

        auto_result = await run_re_scan(
            sample,
            merged,
            worker_router,
            db,
            job_id=job_id,
            re_discover_prompt=re_prompt,
            valid_entity_types=valid_types,
            on_progress=progress_auto_rescan,
            on_event=on_scan_event,
        )
        merged = auto_result.entities
        bus.emit(
            job_id,
            {
                "type": "entities_snapshot",
                "round": "auto_rescan",
                "entities": _merged_entities_snapshot(merged),
            },
        )
        if auto_result.new_canonicals:
            bus.emit(
                job_id,
                {
                    "type": "log",
                    "line": f"自动再识别新增 {len(auto_result.new_canonicals)} 个实体",
                },
            )

        set_job_progress(
            db,
            job,
            phase="entity_leak_verify",
            percent=85,
            message="实体验漏检查中…",
            stats=stats_payload,
            log_line="Worker 检查字面残留…",
        )
        preview_ent_dicts = [
            {
                "canonical_name": e.canonical_name,
                "entity_type": e.entity_type,
                "source": e.source,
                "is_excluded": False,
                "aliases": e.aliases,
            }
            for e in merged
        ]
        preview_text = build_preview_text(
            sample,
            preview_ent_dicts,
            _job_pattern_rules(db, job),
            _job_whitelist_terms(db, job),
            type_prefix_map=_type_prefix_map(db),
        )
        merged, _leaks, _leak_summary = await run_entity_leak_scan(
            preview_text,
            sample,
            merged,
            worker_router,
            db,
            job_id=job_id,
            job_extra=job.prompt_extra,
            on_event=on_scan_event,
        )
        if _leaks:
            bus.emit(
                job_id,
                {
                    "type": "entities_snapshot",
                    "round": "leak_verify",
                    "entities": _merged_entities_snapshot(merged),
                },
            )
    else:
        set_job_progress(
            db,
            job,
            phase="remembered",
            percent=50,
            message="离线模式：仅匹配已记住实体",
            stats=stats_payload,
            log_line="Worker 离线，跳过 AI 识别",
        )
        merged = base_entities
        scan_result = None

    set_job_progress(
        db,
        job,
        phase="merge",
        percent=92,
        message="合并去重实体…",
        stats=stats_payload,
        log_line="合并与去重实体列表…",
        commit=True,
    )
    _clear_auto_entities(db, job_id)
    auto_only = [e for e in merged if e.source != "manual"]
    _persist_merged_entities(db, job_id, auto_only)

    initial_snap = snapshot_entities(merged)
    job.initial_entities_snapshot_json = json.dumps(initial_snap, ensure_ascii=False)
    job.last_re_run_delta_json = json.dumps([], ensure_ascii=False)
    job.re_run_count = 0
    job.experience_eligible = False

    job.scan_entities_json = json.dumps(
        [
            {
                "canonical_name": e.canonical_name,
                "entity_type": e.entity_type,
                "source": e.source,
                "aliases": e.aliases,
                "hit_count": e.hit_count,
            }
            for e in merged
        ],
        ensure_ascii=False,
    )

    scan_summary = {
        "remembered_hits": remembered_hits,
        "llm_hits": len([e for e in merged if e.source == "llm"]),
        "re_run_count": 0,
        "llm_skipped": None if llm_enabled else "llm_disabled",
        "worker_model": scan_metrics.get("model"),
        "offline_only": not llm_enabled,
        "paragraphs": doc_stats["paragraph_count"],
        "chars": doc_stats["char_count"],
        "elapsed_ms": scan_metrics.get("elapsed_ms", 0),
        "prompt_tokens": scan_metrics.get("prompt_tokens", 0),
        "completion_tokens": scan_metrics.get("completion_tokens", 0),
    }
    entity_count = len(list_job_entities(db, job_id))
    set_job_progress(
        db,
        job,
        phase="done",
        percent=100,
        message="初次识别完成",
        stats=stats_payload,
        metrics={
            "elapsed_ms": scan_summary["elapsed_ms"],
            "prompt_tokens": scan_summary["prompt_tokens"],
            "completion_tokens": scan_summary["completion_tokens"],
            "model": scan_summary.get("worker_model"),
        },
        log_line=f"初次识别完成，共发现 {entity_count} 个实体",
        wizard_step="semantic",
        commit=False,
    )
    job.status = "scanned"
    db.commit()
    bus.emit(
        job_id,
        {
            "type": "scan_round_done",
            "round": "initial",
            "entity_count": entity_count,
            "delta": 0,
        },
    )
    bus.emit(
        job_id,
        {
            "type": "done",
            "entity_count": entity_count,
            "scan_summary": scan_summary,
        },
    )
    bus.close(job_id)
    return {
        "job": _job_to_dict(job, db),
        "entities": list_job_entities(db, job_id),
        "scan_summary": scan_summary,
    }


async def re_run_scan_job(
    db: Session,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status not in ("scanned", "semantic_review", "re_scanning"):
        raise HTTPException(400, "当前状态不可再识别")
    if not job.stored_path:
        raise HTTPException(404, "任务未上传文件")
    if not job_needs_worker_queue(db, job, worker_router):
        raise HTTPException(503, "Worker 离线，无法再识别")

    path = resolve_upload_path(job.stored_path)
    sample, _ = extract_doc_sample_and_stats(path)
    base_entities = _job_entities_as_merged(db, job_id)
    manual = [e for e in base_entities if e.source == "manual"]
    auto = [e for e in base_entities if e.source != "manual"]
    base_entities = merge_entities(manual + auto)

    job.status = "re_scanning"
    db.commit()

    bus = get_scan_event_bus()
    bus.clear_history(job_id)
    next_run = (job.re_run_count or 0) + 1
    bus.emit(
        job_id,
        {
            "type": "rescan_start",
            "re_run_count": next_run,
        },
    )
    set_job_progress(
        db,
        job,
        phase="re_discover",
        percent=5,
        message=f"开始第 {next_run} 次再识别…",
        commit=True,
        emit=True,
    )
    re_prompt = get_flow_prompt(db, FLOW_RE_DISCOVER_KEY)
    if job.prompt_extra:
        from app.deid.prompts import JOB_EXTRA_SEPARATOR

        re_prompt = f"{re_prompt}{JOB_EXTRA_SEPARATOR}{job.prompt_extra.strip()}"

    def on_event(ev: dict) -> None:
        bus.emit(job_id, ev)

    def on_progress(c: int, t: int) -> None:
        set_job_progress(
            db,
            job,
            phase="re_discover",
            percent=min(90, 10 + int(80 * c / max(t, 1))),
            message=f"再识别中… {c}/{t}",
            commit=True,
            emit=True,
        )

    result = await run_re_scan(
        sample,
        base_entities,
        worker_router,
        db,
        job_id=job_id,
        re_discover_prompt=re_prompt,
        valid_entity_types=frozenset(valid_codes(db)),
        on_progress=on_progress,
        on_event=on_event,
    )

    _clear_auto_entities(db, job_id)
    auto_only = [e for e in result.entities if e.source != "manual"]
    _persist_merged_entities(db, job_id, auto_only)

    job.re_run_count = (job.re_run_count or 0) + 1
    job.last_re_run_delta_json = json.dumps(result.new_canonicals, ensure_ascii=False)
    job.experience_eligible = len(result.new_canonicals) > 0
    job.status = "scanned"
    db.commit()

    initial = _parse_initial_snapshot(job)
    delta_vs_initial = diff_canonical_vs_initial(initial, result.entities) if initial else []

    bus.emit(
        job_id,
        {
            "type": "entities_snapshot",
            "round": "re_run",
            "entities": _merged_entities_snapshot(result.entities),
        },
    )
    bus.emit(
        job_id,
        {
            "type": "scan_round_done",
            "round": "re_run",
            "entity_count": len(list_job_entities(db, job_id)),
            "delta": len(result.new_canonicals),
            "delta_entities": result.new_canonicals,
            "delta_vs_initial": delta_vs_initial,
            "no_change": len(result.new_canonicals) == 0,
            "re_run_count": job.re_run_count,
            "experience_eligible": job.experience_eligible,
        },
    )

    return {
        "entities": list_job_entities(db, job_id),
        "re_run_count": job.re_run_count,
        "delta": len(result.new_canonicals),
        "delta_entities": result.new_canonicals,
        "no_change": len(result.new_canonicals) == 0,
        "experience_eligible": job.experience_eligible,
    }


async def generate_experience_job(
    db: Session,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if not job.experience_eligible:
        raise HTTPException(400, "当前任务不可提取经验（需再识别产生新实体）")
    if not job_needs_worker_queue(db, job, worker_router):
        raise HTTPException(503, "Worker 离线")

    initial = _parse_initial_snapshot(job)
    if not initial:
        raise HTTPException(400, "缺少初次识别快照")
    if not job.stored_path:
        raise HTTPException(400, "缺少原文件")

    path = resolve_upload_path(job.stored_path)
    sample, _ = extract_doc_sample_and_stats(path)
    current = _job_entities_as_merged(db, job_id)

    line = await run_scan_experience(
        sample,
        initial,
        current,
        worker_router,
        db,
        job_id=job_id,
    )
    if not line:
        return {"text": None, "message": "未生成经验"}
    return {"text": line}


def confirm_experience_job(
    db: Session,
    job_id: int,
    *,
    text: str,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if not job.experience_eligible:
        raise HTTPException(400, "当前任务不可确认经验")

    row = append_global_experience(db, text, source_job_id=job_id)
    job.experience_eligible = False
    db.commit()
    return {"id": row.id, "text": row.text}


def list_global_experience_api(db: Session) -> list[dict]:
    rows = list_global_experience(db)
    return [
        {
            "id": r.id,
            "text": r.text,
            "source_job_id": r.source_job_id,
            "created_at": _dt_iso(r.created_at),
            "updated_at": _dt_iso(r.updated_at),
        }
        for r in rows
    ]


def create_global_experience_api(db: Session, text: str) -> dict:
    row = append_global_experience(db, text, source_job_id=None)
    db.commit()
    return {"id": row.id, "text": row.text}


def patch_global_experience_api(db: Session, exp_id: int, text: str) -> dict:
    row = update_global_experience(db, exp_id, text)
    if not row:
        raise HTTPException(404, "经验不存在")
    db.commit()
    return {"id": row.id, "text": row.text}


def remove_global_experience_api(db: Session, exp_id: int) -> dict:
    if not delete_global_experience(db, exp_id):
        raise HTTPException(404, "经验不存在")
    db.commit()
    return {"deleted": True}


def _job_entities_as_merged(db: Session, job_id: int) -> list[MergedEntity]:
    rows = (
        db.query(DeidJobEntity)
        .filter(DeidJobEntity.job_id == job_id, DeidJobEntity.is_merged.is_(False))
        .all()
    )
    out: list[MergedEntity] = []
    for r in rows:
        aliases = [
            a.alias_text
            for a in db.query(DeidJobEntityAlias).filter(
                DeidJobEntityAlias.job_entity_id == r.id
            )
            if not a.alias_text.startswith(_CONF_ALIAS_PREFIX)
        ]
        out.append(
            MergedEntity(
                canonical_name=r.canonical_name,
                entity_type=r.entity_type,
                source=r.source,
                aliases=aliases or [r.canonical_name],
                hit_count=r.hit_count,
                library_entity_id=r.library_entity_id,
            )
        )
    return out


def _canonical_keys(snapshot: list[dict]) -> set[str]:
    keys: set[str] = set()
    for item in snapshot:
        k = normalize_for_match(item.get("canonical_name") or "")
        if k:
            keys.add(k)
    return keys


def list_job_entities(db: Session, job_id: int) -> list[dict]:
    job = db.get(DeidJob, job_id)
    initial_keys = _canonical_keys(_parse_initial_snapshot(job)) if job else set()

    rows = (
        db.query(DeidJobEntity)
        .filter(DeidJobEntity.job_id == job_id, DeidJobEntity.is_merged.is_(False))
        .all()
    )
    out = []
    for r in rows:
        aliases = [
            a.alias_text
            for a in db.query(DeidJobEntityAlias).filter(
                DeidJobEntityAlias.job_entity_id == r.id
            )
            if not a.alias_text.startswith(_CONF_ALIAS_PREFIX)
        ]
        confidence = _parse_confidence(
            [
                a.alias_text
                for a in db.query(DeidJobEntityAlias).filter(
                    DeidJobEntityAlias.job_entity_id == r.id
                )
            ]
        )
        out.append(
            {
                "id": r.id,
                "canonical_name": r.canonical_name,
                "entity_type": r.entity_type,
                "source": r.source,
                "source_label": SOURCE_UI.get(r.source, r.source),
                "placeholder": r.placeholder,
                "is_excluded": r.is_excluded,
                "hit_count": r.hit_count,
                "aliases": aliases,
                "confidence": confidence,
                "low_confidence": confidence is not None and confidence < 0.5,
                "is_new_since_initial": bool(
                    initial_keys
                    and normalize_for_match(r.canonical_name) not in initial_keys
                ),
            }
        )
    out.sort(key=lambda x: (0 if x["source"] == "manual" else 1, -x["hit_count"]))
    return out


def add_manual_entity(db: Session, job_id: int, body: ManualEntityIn) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if body.entity_type not in valid_codes(db):
        raise HTTPException(400, f"未知实体分类: {body.entity_type}")
    aliases = list(body.aliases) or [body.canonical_name]
    je = DeidJobEntity(
        job_id=job_id,
        entity_type=body.entity_type,
        canonical_name=body.canonical_name,
        source="manual",
        hit_count=0,
        save_to_library=body.save_to_library,
    )
    db.add(je)
    db.flush()
    for a in aliases:
        db.add(DeidJobEntityAlias(job_entity_id=je.id, alias_text=a.strip()))
    if body.save_to_library:
        _persist_manual_to_library(db, job, je, aliases)
    db.commit()
    return list_job_entities(db, job_id)


def _resolve_pack_id(db: Session, job: DeidJob) -> int | None:
    pack_ids = _parse_pack_ids(job)
    if pack_ids:
        return pack_ids[0]
    packs = db.query(DeidClientPack).filter(DeidClientPack.code == "general_finance").first()
    return packs.id if packs else None


def _job_entity_aliases(db: Session, job_entity_id: int) -> list[str]:
    return [
        a.alias_text
        for a in db.query(DeidJobEntityAlias).filter(
            DeidJobEntityAlias.job_entity_id == job_entity_id
        )
        if not a.alias_text.startswith(_CONF_ALIAS_PREFIX)
    ]


def _find_library_entity_in_packs(
    db: Session,
    pack_ids: list[int],
    canonical_name: str,
    aliases: list[str],
) -> DeidEntity | None:
    if not pack_ids:
        return None
    ent = (
        db.query(DeidEntity)
        .filter(
            DeidEntity.pack_id.in_(pack_ids),
            DeidEntity.canonical_name == canonical_name,
            DeidEntity.is_active.is_(True),
        )
        .first()
    )
    if ent:
        return ent
    for alias in aliases:
        row = (
            db.query(DeidEntity)
            .join(DeidEntityAlias, DeidEntityAlias.entity_id == DeidEntity.id)
            .filter(
                DeidEntity.pack_id.in_(pack_ids),
                DeidEntity.is_active.is_(True),
                DeidEntityAlias.alias_text == alias,
            )
            .first()
        )
        if row:
            return row
    return None


def _alias_on_entity(db: Session, entity_id: int, alias_text: str) -> bool:
    if (
        db.query(DeidEntityAlias)
        .filter(
            DeidEntityAlias.entity_id == entity_id,
            DeidEntityAlias.alias_text == alias_text,
        )
        .first()
    ):
        return True
    return any(
        isinstance(obj, DeidEntityAlias)
        and obj.entity_id == entity_id
        and obj.alias_text == alias_text
        for obj in db.new
    )


def _add_aliases_to_entity(
    db: Session,
    entity_id: int,
    aliases: list[str],
    added_from: str,
) -> None:
    seen: set[str] = set()
    for a in aliases:
        text = a.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if _alias_on_entity(db, entity_id, text):
            continue
        conflict = (
            db.query(DeidEntityAlias)
            .filter(
                DeidEntityAlias.alias_text == text,
                DeidEntityAlias.entity_id != entity_id,
            )
            .first()
        )
        if conflict:
            continue
        db.add(
            DeidEntityAlias(
                entity_id=entity_id,
                alias_text=text,
                added_from=added_from,
            )
        )


def _persist_job_entity_to_library(
    db: Session,
    job: DeidJob,
    je: DeidJobEntity,
    aliases: list[str],
    *,
    library_source: str,
    added_from: str,
) -> None:
    pack_ids = _parse_pack_ids(job)
    pack_id = _resolve_pack_id(db, job)
    if not pack_id:
        return

    if je.library_entity_id:
        _add_aliases_to_entity(db, je.library_entity_id, aliases, added_from)
        return

    search_packs = pack_ids if pack_ids else [pack_id]
    existing = _find_library_entity_in_packs(db, search_packs, je.canonical_name, aliases)
    if existing:
        je.library_entity_id = existing.id
        _add_aliases_to_entity(db, existing.id, aliases, added_from)
        return

    prefix = get_placeholder_prefix(db, je.entity_type)
    ent = DeidEntity(
        pack_id=pack_id,
        entity_type=je.entity_type,
        canonical_name=je.canonical_name,
        placeholder_prefix=prefix,
        source=library_source,
        first_seen_job_id=job.id,
    )
    db.add(ent)
    db.flush()
    je.library_entity_id = ent.id
    _add_aliases_to_entity(db, ent.id, aliases, added_from)


def _persist_manual_to_library(
    db: Session, job: DeidJob, je: DeidJobEntity, aliases: list[str]
) -> None:
    _persist_job_entity_to_library(
        db,
        job,
        je,
        aliases,
        library_source="admin",
        added_from="job_manual",
    )


def _persist_llm_entities_to_library(
    db: Session, job: DeidJob, entities: list[DeidJobEntity]
) -> None:
    """Save LLM-discovered entities to the library."""
    for je in entities:
        if je.source != "llm":
            continue
        aliases = _job_entity_aliases(db, je.id)
        if je.canonical_name not in aliases:
            aliases = [je.canonical_name, *aliases]
        _persist_job_entity_to_library(
            db,
            job,
            je,
            aliases,
            library_source="llm",
            added_from="job_llm",
        )


def _persist_active_llm_entities_to_library(db: Session, job: DeidJob) -> None:
    """Persist selected LLM entities to「我的实体」by default."""
    entities = (
        db.query(DeidJobEntity)
        .filter(
            DeidJobEntity.job_id == job.id,
            DeidJobEntity.source == "llm",
            DeidJobEntity.is_excluded.is_(False),
        )
        .all()
    )
    _persist_llm_entities_to_library(db, job, entities)


def patch_job_entity(db: Session, job_id: int, entity_id: int, **kwargs) -> dict:
    je = db.get(DeidJobEntity, entity_id)
    if not je or je.job_id != job_id:
        raise HTTPException(404, "实体不存在")
    if "is_excluded" in kwargs and kwargs["is_excluded"] is not None:
        je.is_excluded = kwargs["is_excluded"]
    if kwargs.get("placeholder"):
        je.placeholder = kwargs["placeholder"]
    db.commit()
    return list_job_entities(db, job_id)


def _apply_entity_selection(
    db: Session,
    job_id: int,
    entity_ids: list[int] | None,
) -> list[DeidJobEntity]:
    rows = db.query(DeidJobEntity).filter(DeidJobEntity.job_id == job_id).all()
    if entity_ids is not None:
        selected = set(entity_ids)
        for r in rows:
            r.is_excluded = r.id not in selected
    return [r for r in rows if not r.is_excluded]


def _type_prefix_map(db: Session) -> dict[str, str]:
    return {code: get_placeholder_prefix(db, code) for code in valid_codes(db)}


def _job_pattern_rules(db: Session, job: DeidJob) -> list[dict]:
    pack_ids = _parse_pack_ids(job)
    return [
        {
            "regex_pattern": r.regex_pattern,
            "placeholder_prefix": r.placeholder_prefix,
            "entity_type": r.entity_type,
            "is_active": r.is_active,
        }
        for r in db.query(DeidPatternRule).filter(DeidPatternRule.is_active.is_(True)).all()
        if not r.pack_id or r.pack_id in pack_ids
    ]


def _job_whitelist_terms(db: Session, job: DeidJob) -> list[dict]:
    pack_ids = _parse_pack_ids(job)
    return [
        {"term": w.term, "term_type": w.term_type, "is_active": w.is_active}
        for w in db.query(DeidWhitelistTerm).filter(DeidWhitelistTerm.is_active.is_(True)).all()
        if not w.pack_id or w.pack_id in pack_ids
    ]


def _build_job_preview_text(
    db: Session,
    job: DeidJob,
    path: Path,
    *,
    max_chars: int = 50000,
) -> str:
    sample = extract_sample_text(path)[:max_chars]
    entities = _entities_for_plan(db, job.id)
    return build_preview_text(
        sample,
        entities,
        _job_pattern_rules(db, job),
        _job_whitelist_terms(db, job),
        type_prefix_map=_type_prefix_map(db),
    )


def _save_semantic_entity_snapshot(db: Session, job: DeidJob, job_id: int) -> None:
    active_ids = sorted(
        r.id
        for r in db.query(DeidJobEntity)
        .filter(DeidJobEntity.job_id == job_id, DeidJobEntity.is_excluded.is_(False))
        .all()
    )
    job.semantic_entity_snapshot_json = json.dumps(active_ids, ensure_ascii=False)


def _semantic_entity_stale(job: DeidJob, active_entity_ids: set[int]) -> bool:
    if not job.semantic_entity_snapshot_json or job.semantic_skipped:
        return False
    try:
        snapshot = set(json.loads(job.semantic_entity_snapshot_json))
    except json.JSONDecodeError:
        return False
    return snapshot != active_entity_ids


def _assign_placeholders(db: Session, job_id: int) -> None:
    entities = (
        db.query(DeidJobEntity)
        .filter(DeidJobEntity.job_id == job_id, DeidJobEntity.is_excluded.is_(False))
        .all()
    )
    ent_dicts = [
        {"id": e.id, "entity_type": e.entity_type, "canonical_name": e.canonical_name}
        for e in entities
    ]
    ph_map = assign_placeholder_map(ent_dicts, type_prefix_map=_type_prefix_map(db))
    for ent in entities:
        if ent.id in ph_map:
            ent.placeholder = ph_map[ent.id]


def _persist_remembered_entities(
    db: Session,
    job: DeidJob,
    remember_ids: list[int] | None,
) -> None:
    if not remember_ids:
        return
    entities = (
        db.query(DeidJobEntity)
        .filter(DeidJobEntity.job_id == job.id, DeidJobEntity.id.in_(remember_ids))
        .all()
    )
    for je in entities:
        aliases = _job_entity_aliases(db, je.id)
        if je.canonical_name not in aliases:
            aliases = [je.canonical_name, *aliases]
        library_source = "llm" if je.source == "llm" else "admin"
        added_from = "job_llm" if je.source == "llm" else "job_manual"
        _persist_job_entity_to_library(
            db,
            job,
            je,
            aliases,
            library_source=library_source,
            added_from=added_from,
        )


def delete_job_entity(db: Session, job_id: int, entity_id: int) -> list[dict]:
    je = db.get(DeidJobEntity, entity_id)
    if not je or je.job_id != job_id:
        raise HTTPException(404, "实体不存在")
    db.query(DeidJobEntityAlias).filter(
        DeidJobEntityAlias.job_entity_id == entity_id
    ).delete()
    db.delete(je)
    db.commit()
    return list_job_entities(db, job_id)


def _parse_semantic_pairs(job: DeidJob) -> list[dict]:
    try:
        raw = json.loads(job.semantic_selection_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    pairs: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("enabled") is False:
            continue
        original = item.get("original") or item.get("risk_original")
        rewritten = item.get("rewritten") or item.get("suggest")
        if original and rewritten and original != rewritten:
            pair: dict[str, Any] = {"original": original, "rewritten": rewritten}
            if item.get("category"):
                pair["category"] = item["category"]
            pairs.append(pair)
    return pairs


async def confirm_job(
    db: Session,
    job_id: int,
    *,
    entity_ids: list[int] | None = None,
    remember_ids: list[int] | None = None,
    semantic_selection: list[dict] | None = None,
    worker_router: WorkerRouter | None = None,
) -> dict:
    """Confirm entities + semantic selection, then finish docx in one pass."""
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status not in ("scanned", "semantic_review", "confirmed"):
        raise HTTPException(400, "请先完成实体扫描与语义扫描")
    active = _apply_entity_selection(db, job_id, entity_ids)
    if not active:
        raise HTTPException(400, "请至少选择一个实体")
    _assign_placeholders(db, job_id)
    _persist_active_llm_entities_to_library(db, job)
    _persist_remembered_entities(db, job, remember_ids)
    if semantic_selection is not None:
        job.semantic_selection_json = json.dumps(semantic_selection, ensure_ascii=False)
    job.preview_ack_at = now_beijing()
    job.status = "confirmed"
    db.commit()
    active_ids = {r.id for r in active}
    stale = _semantic_entity_stale(job, active_ids)
    result = await _execute_deid(db, job, job_id, worker_router=worker_router)
    if stale:
        result["semantic_stale"] = True
    return result


def preview_job(db: Session, job_id: int) -> dict:
    """Return sample replacements (first 5 hits)."""
    job = db.get(DeidJob, job_id)
    if not job or not job.stored_path:
        raise HTTPException(404, "任务不存在")
    path = resolve_upload_path(job.stored_path)
    sample = extract_sample_text(path)[:5000]
    entities = _entities_for_plan(db, job_id)
    from app.deid.engine.plan import build_plan_from_job_entities

    plan = build_plan_from_job_entities(entities, [], [])
    previews = []
    for line in sample.split("\n")[:30]:
        new, cnt = plan.apply_to_text(line)
        if cnt:
            previews.append({"before": line[:120], "after": new[:120]})
        if len(previews) >= 5:
            break
    return {"previews": previews}


def _entities_for_plan(db: Session, job_id: int) -> list[dict]:
    rows = list_job_entities(db, job_id)
    return [
        {
            "id": r["id"],
            "canonical_name": r["canonical_name"],
            "entity_type": r["entity_type"],
            "placeholder": r.get("placeholder"),
            "source": r["source"],
            "is_excluded": r["is_excluded"],
            "aliases": r["aliases"],
        }
        for r in rows
    ]


async def _execute_deid(
    db: Session,
    job: DeidJob,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    if not job.stored_path:
        raise HTTPException(400, "缺少原文件")
    path = resolve_upload_path(job.stored_path)
    out = job_dir(job_id) / f"desensitized_{job.original_filename}"
    entities = _entities_for_plan(db, job_id)
    patterns = _job_pattern_rules(db, job)
    whitelist = _job_whitelist_terms(db, job)

    job.status = "finishing"
    db.commit()

    semantic_pairs = _parse_semantic_pairs(job)
    result = run_deid_pipeline(
        path, out, entities, patterns, whitelist, semantic_pairs=semantic_pairs or None
    )
    if result.get("engine") == "failed":
        job.status = "confirmed"
        db.commit()
        raise HTTPException(500, result.get("error", "脱敏失败"))

    from app.uploads import UPLOADS_DIR

    job.engine = result.get("engine")
    job.output_path = str(out.relative_to(UPLOADS_DIR)).replace("\\", "/")

    pipe_verification = result.get("verification", {})
    semantic_applied = int(result.get("semantic_applied_count") or 0)
    semantic_missed = int(result.get("semantic_missed_count") or 0)
    semantic_missed_samples = result.get("semantic_missed_samples") or []
    semantic_scanned = bool(job.deep_risks_json) and not job.semantic_skipped
    semantic_block: dict[str, Any] = {
        "scanned": semantic_scanned,
        "selected_count": len(semantic_pairs),
        "applied_count": semantic_applied,
        "missed_count": semantic_missed,
        "missed_samples": semantic_missed_samples,
    }
    if semantic_missed > 0:
        missed_cats = {
            normalize_category(s.get("category"))
            for s in semantic_missed_samples
            if s.get("category")
        }
        if missed_cats & HIGH_RISK_CATEGORIES:
            semantic_block["readiness"] = "不建议外发"
        else:
            semantic_block["readiness"] = "部分语义改写未落地"

    worker_online = bool(
        job.use_worker
        and worker_router
        and worker_router.session
        and worker_router.session.state == "ready"
    )
    # 确认阶段只做 XML 替换 + 程序验漏；Worker 验漏仅在实体扫描阶段（entity_leak）使用。
    pipe_verification = merge_verification(
        pipe_verification,
        worker_available=worker_online,
        finish_verify_mode="program_only",
        deep_completed=semantic_scanned and semantic_applied > 0,
        semantic_block=semantic_block,
    )
    job.verification_json = json.dumps(pipe_verification, ensure_ascii=False)
    job.run_summary_json = json.dumps(
        {
            "replacement_count": result.get("replacement_count"),
            "coverage": result.get("coverage"),
            "warning": result.get("warning"),
            "semantic_applied_count": semantic_applied,
            "semantic_skipped": bool(job.semantic_skipped),
        },
        ensure_ascii=False,
    )
    job.status = "done"
    job.completed_at = now_beijing()
    job.expires_at = job.completed_at + timedelta(hours=JOB_RETENTION_HOURS)
    _write_mappings(db, job_id, entities)
    db.commit()
    return {
        "job_id": job_id,
        "status": job.status,
        "engine": job.engine,
        "verification": json.loads(job.verification_json or "{}"),
        "run_summary": json.loads(job.run_summary_json or "{}"),
    }


async def run_job(
    db: Session,
    job_id: int,
    *,
    entity_ids: list[int] | None = None,
    remember_ids: list[int] | None = None,
    worker_router: WorkerRouter | None = None,
) -> dict:
    """Legacy alias — prefer confirm_job."""
    return await confirm_job(
        db,
        job_id,
        entity_ids=entity_ids,
        remember_ids=remember_ids,
        worker_router=worker_router,
    )


async def rerun_job(
    db: Session,
    job_id: int,
    *,
    entity_ids: list[int] | None = None,
    remember_ids: list[int] | None = None,
    worker_router: WorkerRouter | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job or job.status != "done":
        raise HTTPException(400, "只能对已完成的任务重新脱敏")
    active = _apply_entity_selection(db, job_id, entity_ids)
    if not active:
        raise HTTPException(400, "请至少选择一个实体")
    _assign_placeholders(db, job_id)
    _persist_active_llm_entities_to_library(db, job)
    _persist_remembered_entities(db, job, remember_ids)
    db.commit()
    return await _execute_deid(db, job, job_id, worker_router=worker_router)


def _write_mappings(db: Session, job_id: int, entities: list[dict]) -> None:
    db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).delete()
    for ent in entities:
        if ent.get("is_excluded") or not ent.get("placeholder"):
            continue
        for alias in ent.get("aliases", []):
            db.add(
                DeidEntityMapping(
                    job_id=job_id,
                    original_text=alias,
                    placeholder=ent["placeholder"],
                    entity_type=ent["entity_type"],
                    source=ent["source"],
                    hit_count=ent.get("hit_count", 0),
                )
            )


def export_docx(
    db: Session,
    job_id: int,
    *,
    override_ack: bool = False,
    override_reason: str | None = None,
) -> tuple[Path, str]:
    """Return (path, download_filename) for the de-identified docx only."""
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status == "archived":
        raise HTTPException(400, "文件已清理，无法下载")
    if job.status != "done":
        raise HTTPException(400, "任务未完成")
    verification = json.loads(job.verification_json or "{}")
    if not verification.get("passed") and not override_ack:
        raise HTTPException(
            400,
            "验证未通过，请勾选「本人已知晓风险，仍要下载」",
        )
    if override_ack and override_reason:
        job.override_reason = override_reason
        db.commit()

    from app.uploads import UPLOADS_DIR

    out_docx = UPLOADS_DIR / (job.output_path or "")
    if not out_docx.exists():
        raise HTTPException(404, "输出文件不存在")

    mode = get_export_filename_mode(db)
    if mode == "neutral":
        date_str = now_beijing().strftime("%Y%m%d")
        filename = f"deid_{job_id}_{date_str}_desensitized.docx"
    else:
        stem = Path(job.original_filename or "document.docx").stem
        filename = f"{stem}_desensitized.docx"
    return out_docx, filename


def archive_job_files(db: Session, job: DeidJob) -> None:
    """Phase-1 cleanup: remove files, keep mapping for rehydrate."""
    delete_job_files(job.id)
    job.stored_path = None
    job.output_path = None
    job.verification_json = None
    job.run_summary_json = None
    job.status = "archived"
    job.files_purged_at = now_beijing()


def purge_expired_mapping_jobs(db: Session) -> int:
    """Phase-2 cleanup: remove jobs whose mapping retention expired."""
    cutoff = now_beijing() - timedelta(days=MAPPING_RETENTION_DAYS)
    jobs = (
        db.query(DeidJob)
        .filter(
            DeidJob.status == "archived",
            DeidJob.completed_at.isnot(None),
            DeidJob.completed_at < cutoff,
        )
        .all()
    )
    for job in jobs:
        _purge_job(db, job.id, commit=False)
    if jobs:
        db.commit()
    return len(jobs)


def archive_expired_job_files(db: Session) -> int:
    """Phase-1 cleanup: archive done jobs past file retention."""
    cutoff = now_beijing() - timedelta(hours=JOB_RETENTION_HOURS)
    jobs = (
        db.query(DeidJob)
        .filter(
            DeidJob.status == "done",
            DeidJob.completed_at.isnot(None),
            DeidJob.completed_at < cutoff,
        )
        .all()
    )
    for job in jobs:
        archive_job_files(db, job)
    if jobs:
        db.commit()
    return len(jobs)


def _assert_rehydrate_available(db: Session, job: DeidJob) -> None:
    if job.status not in ("done", "archived"):
        raise HTTPException(400, "任务未完成，无法回显")
    meta = _job_rehydrate_meta(db, job)
    if not meta["rehydrate_available"]:
        raise HTTPException(400, "映射已过期或不存在，无法回显")


def get_job_mapping(db: Session, job_id: int) -> list[dict]:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    _assert_rehydrate_available(db, job)
    rows = (
        db.query(DeidEntityMapping)
        .filter(DeidEntityMapping.job_id == job_id)
        .order_by(DeidEntityMapping.placeholder, DeidEntityMapping.original_text)
        .all()
    )
    return [
        {
            "original_text": r.original_text,
            "placeholder": r.placeholder,
            "entity_type": r.entity_type,
            "source": r.source,
            "hit_count": r.hit_count,
        }
        for r in rows
    ]


def rehydrate_job_text(db: Session, job_id: int, text: str) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    _assert_rehydrate_available(db, job)
    rows = db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).all()
    ph_map = build_placeholder_map(rows)
    result = rehydrate_text(text, ph_map)
    return {
        "text": result.text,
        "resolved": result.resolved,
        "unresolved": result.unresolved,
    }


def list_rehydrate_eligible_jobs(db: Session) -> list[dict]:
    mapping_cutoff = now_beijing() - timedelta(days=MAPPING_RETENTION_DAYS)
    jobs = (
        db.query(DeidJob)
        .filter(
            DeidJob.status.in_(("done", "archived")),
            DeidJob.completed_at.isnot(None),
            DeidJob.completed_at >= mapping_cutoff,
        )
        .order_by(DeidJob.completed_at.desc())
        .all()
    )
    out = []
    for job in jobs:
        d = _job_to_dict(job, db)
        if d.get("rehydrate_available"):
            out.append(d)
    return out


def delete_job(db: Session, job_id: int) -> None:
    if not db.get(DeidJob, job_id):
        raise HTTPException(404, "任务不存在")
    _purge_job(db, job_id)


def list_worker_calls(db: Session, job_id: int, *, limit: int = 200) -> dict:
    if not db.get(DeidJob, job_id):
        raise HTTPException(404, "任务不存在")
    from app.deid.worker_call_store import list_worker_calls as _list

    calls = _list(db, job_id, limit=limit)
    return {"job_id": job_id, "total": len(calls), "calls": calls}


def _load_deep_risks(job: DeidJob) -> list[dict]:
    if not job.deep_risks_json:
        return []
    try:
        data = json.loads(job.deep_risks_json)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def get_semantic_risks(db: Session, job_id: int) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status in ("semantic_review", "semantic_scanning", "confirmed", "finishing", "done"):
        return {"risks": _load_deep_risks(job), "status": job.status}
    if job.status == "scanned" and job.deep_risks_json:
        return {"risks": _load_deep_risks(job), "status": "semantic_review"}
    raise HTTPException(400, "语义扫描未完成或不可用")


def get_deep_risks(db: Session, job_id: int) -> dict:
    return get_semantic_risks(db, job_id)


def semantic_skip_job(db: Session, job_id: int) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status not in ("scanned", "semantic_review"):
        raise HTTPException(400, "当前状态不可跳过语义扫描")
    job.semantic_skipped = True
    set_job_progress(
        db,
        job,
        phase="semantic_skipped",
        percent=100,
        message="已跳过语义扫描",
        wizard_step="confirm",
        log_line="用户跳过语义扫描",
    )
    db.commit()
    return {"status": job.status, "semantic_skipped": True}


async def _semantic_generate_rewrites(
    db: Session,
    job: DeidJob,
    job_id: int,
    risks: list[dict],
    sample: str,
    worker_router: WorkerRouter | None,
    *,
    bus,
    start_percent: int = 45,
) -> list[dict]:
    pending = [
        r for r in risks if not (r.get("suggested_rewrite") or r.get("rewritten"))
    ]
    if not pending:
        return risks

    def on_progress(c: int, t: int) -> None:
        set_job_progress(
            db,
            job,
            phase="semantic_suggest",
            percent=min(
                95,
                start_percent + int((95 - start_percent) * c / max(t, 1)),
            ),
            message=f"生成改写建议… {c}/{t}",
            wizard_step="semantic",
            commit=True,
            emit=True,
        )

    def on_event(ev: dict) -> None:
        if ev.get("type") in ("log", "token", "metrics"):
            bus.emit(job_id, ev)

    set_job_progress(
        db,
        job,
        phase="semantic_suggest",
        percent=start_percent,
        message=f"生成改写建议… 0/{len(pending)}",
        wizard_step="semantic",
        log_line=f"逐段检测完成 {len(risks)} 条，补生成缺失改写",
        commit=True,
        emit=True,
    )

    return await run_deep_suggest_all(
        risks,
        sample,
        worker_router,
        db,
        job_id=job_id,
        on_progress=on_progress,
        on_event=on_event,
    )


async def semantic_start_job(
    db: Session,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job or not job.stored_path:
        raise HTTPException(404, "任务不存在或未上传文件")
    if job.status not in ("scanned", "semantic_review"):
        raise HTTPException(400, "请先完成实体扫描")
    if not job.use_worker or not job_needs_worker_queue(db, job, worker_router):
        raise HTTPException(503, "Worker 离线，语义扫描不可用")

    path = resolve_upload_path(job.stored_path)
    if not path.exists():
        raise HTTPException(400, "原文件已丢失")

    job.semantic_skipped = False
    job.status = "semantic_scanning"
    bus = get_scan_event_bus()
    bus.clear_history(job_id)
    set_job_progress(
        db,
        job,
        phase="semantic_detect",
        percent=10,
        message="语义扫描中…",
        wizard_step="semantic",
        log_line="开始语义扫描（检测+改写）",
    )
    _save_semantic_entity_snapshot(db, job, job_id)
    db.commit()

    preview = _build_job_preview_text(db, job, path)

    def on_progress(c: int, t: int) -> None:
        set_job_progress(
            db,
            job,
            phase="semantic_detect",
            percent=min(40, 10 + int(30 * c / max(t, 1))),
            message=f"语义扫描… {c}/{t}",
            wizard_step="semantic",
            commit=True,
            emit=True,
        )

    def on_event(ev: dict) -> None:
        if ev.get("type") in ("log", "token", "metrics", "chunk_start", "risk", "stats"):
            bus.emit(job_id, ev)

    risks, summary = await run_deep_detect(
        preview,
        worker_router,
        db,
        job_id=job_id,
        job_extra=job.prompt_extra,
        scan_chunk_plan=_job_scan_chunk_plan(job),
        on_progress=on_progress,
        on_event=on_event,
    )
    if risks:
        risks = await _semantic_generate_rewrites(
            db,
            job,
            job_id,
            risks,
            preview,
            worker_router,
            bus=bus,
            start_percent=42,
        )
    job.deep_risks_json = json.dumps(risks, ensure_ascii=False)
    job.status = "semantic_review"
    filled = sum(1 for r in risks if r.get("suggested_rewrite") or r.get("rewritten"))
    bus.emit(
        job_id,
        {
            "type": "semantic_done",
            "risk_count": len(risks),
            "rewrite_count": filled,
            "windows": summary.get("windows", 0),
        },
    )
    set_job_progress(
        db,
        job,
        phase="semantic_review",
        percent=100,
        message=(
            f"发现 {len(risks)} 条语义风险，已生成 {filled} 条改写"
            if risks
            else "未发现语义指纹"
        ),
        wizard_step="semantic",
        log_line="语义扫描完成，改写已就绪" if filled else "语义扫描完成",
    )
    db.commit()
    return {"risks": risks, "summary": summary, "status": job.status}


async def semantic_suggest_all_job(
    db: Session,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job or not job.stored_path:
        raise HTTPException(404, "任务不存在或未上传文件")
    if job.status not in ("semantic_review", "confirmed"):
        raise HTTPException(400, "当前状态不可生成改写")
    if not job_needs_worker_queue(db, job, worker_router):
        raise HTTPException(503, "Worker 离线")

    path = resolve_upload_path(job.stored_path)
    if not path.exists():
        raise HTTPException(400, "原文件已丢失")

    risks = _load_deep_risks(job)
    if not risks:
        return {"risks": [], "status": job.status}

    bus = get_scan_event_bus()
    bus.clear_history(job_id)
    prev_status = job.status
    job.status = "semantic_scanning"
    db.commit()

    preview = _build_job_preview_text(db, job, path)
    try:
        risks = await _semantic_generate_rewrites(
            db,
            job,
            job_id,
            risks,
            preview,
            worker_router,
            bus=bus,
            start_percent=15,
        )
        job.deep_risks_json = json.dumps(risks, ensure_ascii=False)
        job.status = "semantic_review"
        filled = sum(1 for r in risks if r.get("suggested_rewrite") or r.get("rewritten"))
        bus.emit(
            job_id,
            {
                "type": "semantic_done",
                "risk_count": len(risks),
                "rewrite_count": filled,
            },
        )
        set_job_progress(
            db,
            job,
            phase="semantic_review",
            percent=100,
            message=f"已生成 {filled} 条改写建议",
            wizard_step="semantic",
            log_line="改写生成完成",
        )
        db.commit()
        return {"risks": risks, "status": job.status}
    except Exception:
        job.status = prev_status
        db.commit()
        raise


async def deep_scan_job(
    db: Session,
    job_id: int,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job or job.status != "done":
        raise HTTPException(400, "请先完成标准脱敏")
    if not job.use_worker or not job_needs_worker_queue(db, job, worker_router):
        raise HTTPException(503, "Worker 离线，深度脱敏不可用")
    if not job.output_path:
        raise HTTPException(400, "缺少输出文件")

    from app.uploads import UPLOADS_DIR

    out_path = UPLOADS_DIR / job.output_path
    if not out_path.exists():
        raise HTTPException(404, "输出文件不存在")

    job.status = "deep_scanning"
    db.commit()

    sample = extract_sample_text(out_path)[:50000]
    risks, summary = await run_deep_detect(
        sample,
        worker_router,
        db,
        job_id=job_id,
        job_extra=job.prompt_extra,
        scan_chunk_plan=_job_scan_chunk_plan(job),
    )
    job.deep_risks_json = json.dumps(risks, ensure_ascii=False)
    job.status = "deep_review" if risks else "done"
    db.commit()
    return {"risks": risks, "summary": summary, "status": job.status}


async def semantic_suggest_risk(
    db: Session,
    job_id: int,
    risk_id: str,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status not in ("semantic_review", "confirmed"):
        raise HTTPException(400, "当前状态不支持语义改写建议")
    risks = _load_deep_risks(job)
    risk = find_risk_by_id(risks, risk_id)
    if not risk:
        raise HTTPException(404, "风险项不存在")
    if risk.get("suggested_rewrite"):
        return {"risk_id": risk_id, "suggested_rewrite": risk["suggested_rewrite"]}

    if not job_needs_worker_queue(db, job, worker_router):
        raise HTTPException(503, "Worker 离线")

    path = resolve_upload_path(job.stored_path) if job.stored_path else None
    preview = (
        _build_job_preview_text(db, job, path)
        if path and path.exists()
        else ""
    )
    suggestion = await run_deep_suggest(
        risk, preview, worker_router, db, job_id=job_id
    )
    if suggestion:
        risks = update_risk_in_list(risks, risk_id, {"suggested_rewrite": suggestion})
        job.deep_risks_json = json.dumps(risks, ensure_ascii=False)
        db.commit()
    return {"risk_id": risk_id, "suggested_rewrite": suggestion}


async def deep_suggest_risk(
    db: Session,
    job_id: int,
    risk_id: str,
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    return await semantic_suggest_risk(
        db, job_id, risk_id, worker_router=worker_router
    )


async def deep_apply_job(
    db: Session,
    job_id: int,
    items: list[dict],
    *,
    worker_router: WorkerRouter | None = None,
) -> dict:
    raise HTTPException(
        410,
        "深度脱敏写回已废弃，请在确认阶段通过 semantic_selection 一次性完成",
    )


def get_scan_prompt_settings(db: Session) -> dict:
    from app.deid.settings_store import ensure_default_scan_prompt

    ensure_default_scan_prompt(db)
    return scan_prompt_meta(db)


def update_scan_prompt(db: Session, prompt: str) -> dict:
    text = (prompt or "").strip()
    if not text:
        raise HTTPException(400, "提示词不能为空")
    set_setting(db, SCAN_PROMPT_SETTING_KEY, text)
    return scan_prompt_meta(db)


def reset_scan_prompt_settings(db: Session) -> dict:
    reset_scan_prompt(db)
    return scan_prompt_meta(db)


def get_job_effective_prompt(db: Session, job_id: int) -> dict:
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    global_prompt = get_scan_prompt(db)
    return {
        "global_prompt": global_prompt,
        "prompt_extra": job.prompt_extra,
        "effective_prompt": build_scan_system_prompt(
            global_prompt,
            job.prompt_extra,
            entity_types=list_entity_types(db),
        ),
        "default_prompt": DEFAULT_SCAN_PROMPT,
    }
