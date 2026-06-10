"""Global experience lines for initial entity discovery."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models_deid import DeidGlobalExperience
from app.time_utils import now_beijing

_GLOBAL_MAX = 20
_INJECT_MAX = 10


def list_global_experience(db: Session, *, limit: int | None = None) -> list[DeidGlobalExperience]:
    q = db.query(DeidGlobalExperience).order_by(DeidGlobalExperience.id.desc())
    if limit is not None:
        q = q.limit(limit)
    return list(q.all())


def list_global_experience_texts(db: Session, *, limit: int = _INJECT_MAX) -> list[str]:
    rows = list_global_experience(db, limit=limit)
    return [r.text.strip() for r in reversed(rows) if r.text.strip()]


def append_global_experience(
    db: Session,
    text: str,
    *,
    source_job_id: int | None = None,
) -> DeidGlobalExperience:
    cleaned = text.strip()[:100]
    if not cleaned:
        raise ValueError("经验不能为空")
    row = DeidGlobalExperience(
        text=cleaned,
        source_job_id=source_job_id,
        created_at=now_beijing(),
        updated_at=now_beijing(),
    )
    db.add(row)
    db.flush()
    _trim_fifo(db)
    return row


def update_global_experience(db: Session, exp_id: int, text: str) -> DeidGlobalExperience | None:
    row = db.get(DeidGlobalExperience, exp_id)
    if not row:
        return None
    cleaned = text.strip()[:100]
    if not cleaned:
        raise ValueError("经验不能为空")
    row.text = cleaned
    row.updated_at = now_beijing()
    return row


def delete_global_experience(db: Session, exp_id: int) -> bool:
    row = db.get(DeidGlobalExperience, exp_id)
    if not row:
        return False
    db.delete(row)
    return True


def _trim_fifo(db: Session) -> None:
    rows = (
        db.query(DeidGlobalExperience)
        .order_by(DeidGlobalExperience.id.asc())
        .all()
    )
    overflow = len(rows) - _GLOBAL_MAX
    if overflow <= 0:
        return
    for row in rows[:overflow]:
        db.delete(row)


def build_experience_prompt_block(lines: list[str] | None) -> str:
    if not lines:
        return ""
    merged: list[str] = []
    seen: set[str] = set()
    for line in lines:
        key = line.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(line.strip())
        if len(merged) >= _INJECT_MAX:
            break
    if not merged:
        return ""
    body = "\n".join(f"- {line}" for line in merged)
    return f"\n\n--- 历史经验（最近{len(merged)}条）---\n{body}"
