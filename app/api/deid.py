"""REST API for financial document de-identification."""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deid import service
from app.deid.schemas import (
    AliasIn,
    ConfirmIn,
    EntityTypeIn,
    EntityTypePatch,
    LibraryEntityIn,
    LibraryEntityPatch,
    ManualEntityIn,
    MergeEntitiesIn,
    PatternRuleIn,
    PatternTestIn,
    RunIn,
    ScanPromptIn,
    WhitelistIn,
)
from app.deid.engine.plan import normalize_for_match
from app.models_deid import (
    DeidClientPack,
    DeidEntity,
    DeidEntityAlias,
    DeidJob,
    DeidPatternRule,
    DeidWhitelistTerm,
)

router = APIRouter(prefix="/api/deid", tags=["deid"])


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    return service.list_jobs(db)


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    return service.get_job(db, job_id)


@router.post("/jobs/{job_id}/start")
async def start_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    from fastapi import HTTPException

    queue = getattr(request.app.state, "scan_queue", None)
    if not queue:
        raise HTTPException(503, "扫描队列未就绪")
    job = db.get(DeidJob, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status not in ("draft", "scanned", "confirmed", "done"):
        raise HTTPException(400, "任务状态不允许开始扫描")
    result = await queue.submit(job_id)
    return {"job_id": job_id, **result}


@router.get("/queue/status")
def queue_status(request: Request):
    queue = getattr(request.app.state, "scan_queue", None)
    if not queue:
        return {"current_job_id": None, "waiting_job_ids": [], "waiting_count": 0}
    return queue.status_dict()


@router.post("/jobs")
async def create_job(
    file: UploadFile = File(...),
    pack_ids: str | None = Form(None),
    prompt_extra: str | None = Form(None),
    use_worker: str | None = Form("true"),
    db: Session = Depends(get_db),
):
    ids = None
    if pack_ids:
        ids = json.loads(pack_ids)
    use = use_worker is None or use_worker.strip().lower() not in ("0", "false", "off", "no")
    return await service.create_job(db, file, ids, prompt_extra=prompt_extra, use_worker=use)


@router.get("/settings/scan-prompt")
def get_scan_prompt_settings(db: Session = Depends(get_db)):
    return service.get_scan_prompt_settings(db)


@router.put("/settings/scan-prompt")
def update_scan_prompt(body: ScanPromptIn, db: Session = Depends(get_db)):
    return service.update_scan_prompt(db, body.prompt)


@router.post("/settings/scan-prompt/reset")
def reset_scan_prompt_settings(db: Session = Depends(get_db)):
    return service.reset_scan_prompt_settings(db)


@router.get("/jobs/{job_id}/effective-prompt")
def get_effective_prompt(job_id: int, db: Session = Depends(get_db)):
    return service.get_job_effective_prompt(db, job_id)


@router.post("/jobs/{job_id}/scan")
async def scan_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    router = getattr(request.app.state, "worker_router", None)
    return await service.scan_job(db, job_id, worker_router=router)


@router.post("/jobs/{job_id}/rescan")
async def rescan_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    router = getattr(request.app.state, "worker_router", None)
    return await service.scan_job(db, job_id, worker_router=router)


@router.get("/worker/status")
def worker_status(request: Request):
    router = getattr(request.app.state, "worker_router", None)
    if not router:
        return {"online": False, "state": "offline", "model": None, "hostname": None, "version": None}
    return router.status_dict()


@router.get("/jobs/{job_id}/entities")
def get_entities(job_id: int, db: Session = Depends(get_db)):
    return service.list_job_entities(db, job_id)


@router.post("/jobs/{job_id}/entities")
def add_entity(job_id: int, body: ManualEntityIn, db: Session = Depends(get_db)):
    return service.add_manual_entity(db, job_id, body)


@router.patch("/jobs/{job_id}/entities/{entity_id}")
def patch_entity(
    job_id: int,
    entity_id: int,
    body: dict,
    db: Session = Depends(get_db),
):
    return service.patch_job_entity(
        db,
        job_id,
        entity_id,
        is_excluded=body.get("is_excluded"),
        placeholder=body.get("placeholder"),
    )


@router.delete("/jobs/{job_id}/entities/{entity_id}")
def delete_entity(job_id: int, entity_id: int, db: Session = Depends(get_db)):
    return service.delete_job_entity(db, job_id, entity_id)


@router.post("/jobs/{job_id}/preview")
def preview(job_id: int, db: Session = Depends(get_db)):
    return service.preview_job(db, job_id)


@router.post("/jobs/{job_id}/confirm")
def confirm(job_id: int, body: ConfirmIn | None = None, db: Session = Depends(get_db)):
    remember_ids = body.remember_ids if body else None
    entity_ids = body.entity_ids if body else None
    return service.confirm_job(db, job_id, entity_ids=entity_ids, remember_ids=remember_ids)


@router.post("/jobs/{job_id}/run")
def run(job_id: int, body: RunIn | None = None, db: Session = Depends(get_db)):
    remember_ids = body.remember_ids if body else None
    entity_ids = body.entity_ids if body else None
    return service.run_job(db, job_id, entity_ids=entity_ids, remember_ids=remember_ids)


@router.post("/jobs/{job_id}/rerun")
def rerun(job_id: int, body: RunIn | None = None, db: Session = Depends(get_db)):
    remember_ids = body.remember_ids if body else None
    entity_ids = body.entity_ids if body else None
    return service.rerun_job(db, job_id, entity_ids=entity_ids, remember_ids=remember_ids)


@router.post("/jobs/{job_id}/ai-summary")
async def ai_summary(job_id: int, request: Request, db: Session = Depends(get_db)):
    router = getattr(request.app.state, "worker_router", None)
    return await service.generate_job_ai_summary(db, job_id, worker_router=router)


@router.get("/jobs/{job_id}/export")
def export_job(
    job_id: int,
    override_ack: bool = Query(False),
    override_reason: str | None = Query(None),
    db: Session = Depends(get_db),
):
    path, filename = service.export_docx(
        db,
        job_id,
        override_ack=override_ack,
        override_reason=override_reason,
    )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    service.delete_job(db, job_id)
    return {"ok": True}


# ── Library ──────────────────────────────────────────────────────────────────


@router.get("/entity-types")
def list_entity_types_api(db: Session = Depends(get_db)):
    from app.deid import entity_types as et

    return et.list_entity_types(db)


@router.post("/entity-types")
def create_entity_type_api(body: EntityTypeIn, db: Session = Depends(get_db)):
    from app.deid import entity_types as et

    return et.create_entity_type(db, body.code, body.label, body.placeholder_prefix)


@router.patch("/entity-types/{code}")
def patch_entity_type_api(code: str, body: EntityTypePatch, db: Session = Depends(get_db)):
    from app.deid import entity_types as et

    return et.update_entity_type(
        db,
        code,
        label=body.label,
        placeholder_prefix=body.placeholder_prefix,
    )


@router.delete("/entity-types/{code}")
def delete_entity_type_api(code: str, db: Session = Depends(get_db)):
    from app.deid import entity_types as et

    et.delete_entity_type(db, code)
    return {"ok": True}


@router.get("/packs")
def list_packs(db: Session = Depends(get_db)):
    packs = db.query(DeidClientPack).filter(DeidClientPack.is_active.is_(True)).all()
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "is_default": p.is_default,
        }
        for p in packs
    ]


@router.get("/entities")
def list_entities(
    pack_id: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(DeidEntity).filter(DeidEntity.is_active.is_(True))
    if pack_id:
        query = query.filter(DeidEntity.pack_id == pack_id)
    rows = query.order_by(DeidEntity.canonical_name).limit(500).all()
    out = []
    for e in rows:
        if q and q not in e.canonical_name:
            continue
        aliases = [
            a.alias_text
            for a in db.query(DeidEntityAlias).filter(DeidEntityAlias.entity_id == e.id)
        ]
        out.append(
            {
                "id": e.id,
                "pack_id": e.pack_id,
                "canonical_name": e.canonical_name,
                "entity_type": e.entity_type,
                "placeholder_prefix": e.placeholder_prefix,
                "source": e.source,
                "times_hit_total": e.times_hit_total,
                "aliases": aliases,
            }
        )
    return out


@router.get("/entities/recent")
def recent_entities(db: Session = Depends(get_db)):
    from datetime import timedelta

    from app.time_utils import now_beijing

    cutoff = now_beijing() - timedelta(days=30)
    aliases = (
        db.query(DeidEntityAlias)
        .filter(
            DeidEntityAlias.added_from.in_(("admin", "job_manual")),
        )
        .limit(50)
        .all()
    )
    ent_ids = {a.entity_id for a in aliases}
    ents = db.query(DeidEntity).filter(DeidEntity.id.in_(ent_ids)).all() if ent_ids else []
    return [
        {
            "id": e.id,
            "canonical_name": e.canonical_name,
            "times_hit_total": e.times_hit_total,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in ents
        if e.created_at and e.created_at >= cutoff
    ]


@router.post("/entities")
def create_entity(body: LibraryEntityIn, db: Session = Depends(get_db)):
    from app.deid.entity_types import ensure_default_entity_types, get_placeholder_prefix, valid_codes

    ensure_default_entity_types(db)
    if body.entity_type not in valid_codes(db):
        from fastapi import HTTPException

        raise HTTPException(400, f"未知实体分类: {body.entity_type}")
    prefix = get_placeholder_prefix(db, body.entity_type)
    ent = DeidEntity(
        pack_id=body.pack_id,
        entity_type=body.entity_type,
        canonical_name=body.canonical_name,
        placeholder_prefix=prefix,
        source="admin",
    )
    db.add(ent)
    db.flush()
    for a in body.aliases or [body.canonical_name]:
        norm = normalize_for_match(a)
        dup = db.query(DeidEntityAlias).filter(DeidEntityAlias.alias_text == a).first()
        if dup:
            from fastapi import HTTPException

            raise HTTPException(400, f"别名「{a}」已属于其它实体")
        db.add(DeidEntityAlias(entity_id=ent.id, alias_text=a, added_from="admin"))
    db.commit()
    return {"id": ent.id}


@router.patch("/entities/{entity_id}")
def patch_entity_lib(entity_id: int, body: LibraryEntityPatch, db: Session = Depends(get_db)):
    ent = db.get(DeidEntity, entity_id)
    if not ent:
        from fastapi import HTTPException

        raise HTTPException(404, "实体不存在")
    if body.canonical_name is not None:
        ent.canonical_name = body.canonical_name
    if body.entity_type is not None:
        from app.deid.entity_types import valid_codes

        if body.entity_type not in valid_codes(db):
            from fastapi import HTTPException

            raise HTTPException(400, f"未知实体分类: {body.entity_type}")
        ent.entity_type = body.entity_type
    if body.is_active is not None:
        ent.is_active = body.is_active
    if body.notes is not None:
        ent.notes = body.notes
    db.commit()
    return {"ok": True}


@router.delete("/entities/{entity_id}")
def delete_entity_lib(entity_id: int, db: Session = Depends(get_db)):
    ent = db.get(DeidEntity, entity_id)
    if ent:
        ent.is_active = False
        db.commit()
    return {"ok": True}


@router.post("/entities/{entity_id}/aliases")
def add_alias(entity_id: int, body: AliasIn, db: Session = Depends(get_db)):
    dup = (
        db.query(DeidEntityAlias)
        .filter(DeidEntityAlias.alias_text == body.alias_text)
        .first()
    )
    if dup:
        from fastapi import HTTPException

        raise HTTPException(400, "别名已存在")
    db.add(DeidEntityAlias(entity_id=entity_id, alias_text=body.alias_text, added_from="admin"))
    db.commit()
    return {"ok": True}


@router.delete("/entities/{entity_id}/aliases/{alias_id}")
def delete_alias(entity_id: int, alias_id: int, db: Session = Depends(get_db)):
    row = db.get(DeidEntityAlias, alias_id)
    if row and row.entity_id == entity_id:
        db.delete(row)
        db.commit()
    return {"ok": True}


@router.post("/entities/merge")
def merge_entities(body: MergeEntitiesIn, db: Session = Depends(get_db)):
    target = db.get(DeidEntity, body.target_entity_id)
    if not target:
        from fastapi import HTTPException

        raise HTTPException(404, "目标实体不存在")
    for sid in body.source_entity_ids:
        src = db.get(DeidEntity, sid)
        if src and src.id != target.id:
            for a in db.query(DeidEntityAlias).filter(DeidEntityAlias.entity_id == src.id):
                a.entity_id = target.id
            src.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/pattern-rules")
def list_rules(db: Session = Depends(get_db)):
    return [
        {
            "id": r.id,
            "name": r.name,
            "regex_pattern": r.regex_pattern,
            "entity_type": r.entity_type,
            "placeholder_prefix": r.placeholder_prefix,
            "pack_id": r.pack_id,
            "priority": r.priority,
            "is_active": r.is_active,
        }
        for r in db.query(DeidPatternRule).all()
    ]


@router.post("/pattern-rules")
def create_rule(body: PatternRuleIn, db: Session = Depends(get_db)):
    r = DeidPatternRule(**body.model_dump())
    db.add(r)
    db.commit()
    return {"id": r.id}


@router.patch("/pattern-rules/{rule_id}")
def patch_rule(rule_id: int, body: dict, db: Session = Depends(get_db)):
    r = db.get(DeidPatternRule, rule_id)
    if not r:
        from fastapi import HTTPException

        raise HTTPException(404)
    for k, v in body.items():
        if hasattr(r, k):
            setattr(r, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/pattern-rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    r = db.get(DeidPatternRule, rule_id)
    if r:
        r.is_active = False
        db.commit()
    return {"ok": True}


@router.post("/pattern-rules/test")
def test_rule(body: PatternTestIn):
    import re

    try:
        matches = [m.group() for m in re.finditer(body.regex_pattern, body.sample_text)]
        return {"matches": matches[:20]}
    except re.error as e:
        return {"error": str(e), "matches": []}


@router.get("/whitelist")
def list_whitelist(db: Session = Depends(get_db)):
    return [
        {
            "id": w.id,
            "term": w.term,
            "term_type": w.term_type,
            "category": w.category,
            "pack_id": w.pack_id,
            "is_active": w.is_active,
        }
        for w in db.query(DeidWhitelistTerm).all()
    ]


@router.post("/whitelist")
def create_whitelist(body: WhitelistIn, db: Session = Depends(get_db)):
    w = DeidWhitelistTerm(**body.model_dump())
    db.add(w)
    db.commit()
    return {"id": w.id}


@router.patch("/whitelist/{term_id}")
def patch_whitelist(term_id: int, body: dict, db: Session = Depends(get_db)):
    w = db.get(DeidWhitelistTerm, term_id)
    if w:
        for k, v in body.items():
            if hasattr(w, k):
                setattr(w, k, v)
        db.commit()
    return {"ok": True}


@router.delete("/whitelist/{term_id}")
def delete_whitelist(term_id: int, db: Session = Depends(get_db)):
    w = db.get(DeidWhitelistTerm, term_id)
    if w:
        w.is_active = False
        db.commit()
    return {"ok": True}
