"""De-identification job state machine and library operations."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.deid.discovery.enrich import enrich_discovered_entities
from app.deid.discovery.llm import count_llm_chunks, discover_llm
from app.deid.discovery.merge import MergedEntity, merge_entities
from app.deid.engine.pipeline import extract_doc_sample_and_stats, extract_sample_text, run_deid_pipeline
from app.deid.engine.plan import normalize_for_match
from app.deid.prompts import build_scan_system_prompt
from app.deid.entity_types import get_placeholder_prefix, list_entity_types, valid_codes
from app.deid.schemas import ManualEntityIn
from app.deid.scan_events import get_scan_event_bus
from app.deid.settings_store import get_scan_prompt, reset_scan_prompt, scan_prompt_meta, set_setting
from app.deid.prompts import DEFAULT_SCAN_PROMPT, SCAN_PROMPT_SETTING_KEY
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

_AUTO_SOURCES = frozenset({"llm", "remembered"})
_CONF_ALIAS_PREFIX = "__conf:"


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
        "progress": _parse_progress(job),
        "files_purged_at": None,
        "mapping_expires_at": None,
        "rehydrate_available": False,
    }
    if db is not None:
        out.update(_job_rehydrate_meta(db, job))
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
    llm_chunk_count = count_llm_chunks(sample)
    stats_payload = {
        "paragraphs": doc_stats["paragraph_count"],
        "chars": doc_stats["char_count"],
        "tables": doc_stats["table_count"],
        "chunks": llm_chunk_count,
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

    llm_entities: list[MergedEntity] = []
    llm_result = None
    llm_enabled = job.use_worker and job_needs_worker_queue(db, job, worker_router)

    if llm_enabled:
        scan_metrics: dict[str, Any] = {"model": None}
        llm_percent = 30

        def on_llm_progress(current: int, total: int) -> None:
            nonlocal llm_percent
            if total <= 0:
                return
            llm_percent = 30 + int(60 * current / total)
            set_job_progress(
                db,
                job,
                phase="llm",
                percent=llm_percent,
                message=f"AI 识别 {current}/{total}",
                stats=stats_payload,
                metrics=scan_metrics if scan_metrics.get("model") else None,
                commit=True,
                emit=False,
            )
            bus.emit(
                job_id,
                {
                    "type": "phase",
                    "phase": "llm",
                    "percent": llm_percent,
                    "message": f"AI 识别 {current}/{total}",
                },
            )

        def on_llm_event(event: dict) -> None:
            bus.emit(job_id, event)
            if event.get("type") == "metrics":
                scan_metrics.update(event)
                set_job_progress(
                    db,
                    job,
                    phase="llm",
                    percent=llm_percent,
                    message="AI 识别中…",
                    stats=stats_payload,
                    metrics=scan_metrics,
                    commit=True,
                    emit=False,
                )
            elif event.get("type") == "log":
                set_job_progress(
                    db,
                    job,
                    phase="llm",
                    percent=llm_percent,
                    message="AI 识别中…",
                    stats=stats_payload,
                    metrics=scan_metrics if scan_metrics.get("model") else None,
                    log_line=str(event.get("line") or ""),
                    commit=True,
                    emit=False,
                )
            elif event.get("type") == "entity":
                set_job_progress(
                    db,
                    job,
                    phase="llm",
                    percent=llm_percent,
                    message="AI 识别中…",
                    stats=stats_payload,
                    metrics=scan_metrics if scan_metrics.get("model") else None,
                    log_line=f"发现实体：{event.get('name')}",
                    commit=True,
                    emit=False,
                )

        set_job_progress(
            db,
            job,
            phase="llm",
            percent=30,
            message="AI 识别…",
            stats=stats_payload,
            log_line="启动 AI 模型识别…",
        )
        llm_result = await discover_llm(
            sample,
            worker_router,
            job_id=job_id,
            system_prompt=build_scan_system_prompt(
                get_scan_prompt(db),
                job.prompt_extra,
                entity_types=list_entity_types(db),
            ),
            enabled=True,
            on_progress=on_llm_progress,
            on_event=on_llm_event,
            valid_entity_types=frozenset(valid_codes(db)),
        )
        if llm_result.worker_model:
            scan_metrics["model"] = llm_result.worker_model
        scan_metrics.update(
            {
                "elapsed_ms": llm_result.elapsed_ms,
                "prompt_tokens": llm_result.prompt_tokens,
                "completion_tokens": llm_result.completion_tokens,
            }
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

    combined_raw = list(llm_result.entities) if llm_result else []
    if sample:
        enrich_discovered_entities(sample, combined_raw)
        if combined_raw:
            bus.emit(
                job_id,
                {
                    "type": "log",
                    "line": f"上下文关联完成，共 {len(combined_raw)} 个实体（含别名扩展）",
                },
            )

    llm_entities = [
        MergedEntity(
            canonical_name=e.canonical_name,
            entity_type=e.entity_type,
            source=e.source,
            aliases=e.aliases or [e.canonical_name],
            hit_count=e.hit_count,
            confidence=e.confidence,
        )
        for e in combined_raw
    ]

    all_discovered = remembered_entities + llm_entities
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
    merged = merge_entities(manual_merged + all_discovered)

    _clear_auto_entities(db, job_id)
    auto_only = [e for e in merged if e.source != "manual"]
    _persist_merged_entities(db, job_id, auto_only)

    llm_hits = len(llm_result.entities) if llm_result else 0
    scan_summary = {
        "remembered_hits": remembered_hits,
        "llm_hits": llm_hits,
        "llm_chunks": llm_result.chunks if llm_result else 0,
        "llm_skipped": llm_result.skipped if llm_result else "llm_disabled",
        "worker_model": llm_result.worker_model if llm_result else None,
        "llm_errors": llm_result.errors if llm_result else [],
        "offline_only": not llm_enabled,
        "paragraphs": doc_stats["paragraph_count"],
        "chars": doc_stats["char_count"],
        "elapsed_ms": llm_result.elapsed_ms if llm_result else 0,
        "prompt_tokens": llm_result.prompt_tokens if llm_result else 0,
        "completion_tokens": llm_result.completion_tokens if llm_result else 0,
    }
    entity_count = len(list_job_entities(db, job_id))
    set_job_progress(
        db,
        job,
        phase="done",
        percent=100,
        message="解析完成",
        stats=stats_payload,
        metrics={
            "elapsed_ms": scan_summary["elapsed_ms"],
            "prompt_tokens": scan_summary["prompt_tokens"],
            "completion_tokens": scan_summary["completion_tokens"],
            "model": scan_summary.get("worker_model"),
        },
        log_line=f"扫描完成，共发现 {entity_count} 个实体",
        commit=False,
    )
    job.status = "scanned"
    db.commit()
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


def list_job_entities(db: Session, job_id: int) -> list[dict]:
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


def _add_aliases_to_entity(
    db: Session,
    entity_id: int,
    aliases: list[str],
    added_from: str,
) -> None:
    for a in aliases:
        text = a.strip()
        if not text:
            continue
        conflict = (
            db.query(DeidEntityAlias).filter(DeidEntityAlias.alias_text == text).first()
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


def _assign_placeholders(db: Session, job_id: int) -> None:
    entities = (
        db.query(DeidJobEntity)
        .filter(DeidJobEntity.job_id == job_id, DeidJobEntity.is_excluded.is_(False))
        .all()
    )
    counters: dict[str, int] = {}
    for ent in sorted(entities, key=lambda e: (e.entity_type, e.canonical_name)):
        prefix = get_placeholder_prefix(db, ent.entity_type)
        counters[prefix] = counters.get(prefix, 0) + 1
        ent.placeholder = f"[{prefix}_{counters[prefix]}]"


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


def confirm_job(
    db: Session,
    job_id: int,
    *,
    entity_ids: list[int] | None = None,
    remember_ids: list[int] | None = None,
) -> list[dict]:
    """Deprecated thin wrapper — assigns placeholders without running pipeline."""
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    active = _apply_entity_selection(db, job_id, entity_ids)
    if not active:
        raise HTTPException(400, "请至少选择一个实体")
    _assign_placeholders(db, job_id)
    _persist_active_llm_entities_to_library(db, job)
    _persist_remembered_entities(db, job, remember_ids)
    job.status = "confirmed"
    job.preview_ack_at = now_beijing()
    db.commit()
    return list_job_entities(db, job_id)


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
            "canonical_name": r["canonical_name"],
            "entity_type": r["entity_type"],
            "placeholder": r.get("placeholder"),
            "source": r["source"],
            "is_excluded": r["is_excluded"],
            "aliases": r["aliases"],
        }
        for r in rows
    ]


def _execute_deid(db: Session, job: DeidJob, job_id: int) -> dict:
    if not job.stored_path:
        raise HTTPException(400, "缺少原文件")
    path = resolve_upload_path(job.stored_path)
    out = job_dir(job_id) / f"desensitized_{job.original_filename}"
    entities = _entities_for_plan(db, job_id)
    pack_ids = _parse_pack_ids(job)
    patterns = [
        {
            "regex_pattern": r.regex_pattern,
            "placeholder_prefix": r.placeholder_prefix,
            "entity_type": r.entity_type,
            "is_active": r.is_active,
        }
        for r in db.query(DeidPatternRule).filter(DeidPatternRule.is_active.is_(True)).all()
        if not r.pack_id or r.pack_id in pack_ids
    ]
    whitelist = [
        {"term": w.term, "term_type": w.term_type, "is_active": w.is_active}
        for w in db.query(DeidWhitelistTerm).filter(DeidWhitelistTerm.is_active.is_(True)).all()
        if not w.pack_id or w.pack_id in pack_ids
    ]

    job.status = "running"
    db.commit()

    result = run_deid_pipeline(path, out, entities, patterns, whitelist)
    if result.get("engine") == "failed":
        job.status = "scanned" if job.preview_ack_at else "scanned"
        db.commit()
        raise HTTPException(500, result.get("error", "脱敏失败"))

    from app.uploads import UPLOADS_DIR

    job.engine = result.get("engine")
    job.output_path = str(out.relative_to(UPLOADS_DIR)).replace("\\", "/")
    job.verification_json = json.dumps(result.get("verification", {}), ensure_ascii=False)
    job.run_summary_json = json.dumps(
        {
            "replacement_count": result.get("replacement_count"),
            "coverage": result.get("coverage"),
            "warning": result.get("warning"),
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


def run_job(
    db: Session,
    job_id: int,
    *,
    entity_ids: list[int] | None = None,
    remember_ids: list[int] | None = None,
) -> dict:
    job = db.get(DeidJob, job_id)
    if not job or job.status not in ("scanned", "confirmed"):
        raise HTTPException(400, "请先完成扫描并确认实体")
    active = _apply_entity_selection(db, job_id, entity_ids)
    if not active:
        raise HTTPException(400, "请至少选择一个实体")
    _assign_placeholders(db, job_id)
    _persist_active_llm_entities_to_library(db, job)
    _persist_remembered_entities(db, job, remember_ids)
    db.commit()
    return _execute_deid(db, job, job_id)


def rerun_job(
    db: Session,
    job_id: int,
    *,
    entity_ids: list[int] | None = None,
    remember_ids: list[int] | None = None,
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
    return _execute_deid(db, job, job_id)


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
