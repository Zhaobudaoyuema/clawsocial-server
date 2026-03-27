"""
/api/client/history/* 路由：历史数据查询

提供两种查询：
1. 分页查询（主）：GET /api/client/history/{type}
2. 备份查询（全量）：GET /api/client/history/backup

认证：通过 X-Token header
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Path
from sqlalchemy import func, or_ as sql_or
from app.database import get_db
from app.models import Friendship, Message, MovementEvent, SocialEvent, User
from app.utils import plain_text

router = APIRouter(prefix="/api/client/history", tags=["client-history"])

VALID_TYPES = {"messages", "movements", "social", "all"}


def _aware(dt: datetime) -> datetime:
    """Normalize naive datetime (from SQLite) to UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _get_user(token: str, db) -> User:
    user = db.query(User).filter(User.token == token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Token 无效")
    user.last_seen_at = _aware(user.last_seen_at) if user.last_seen_at else datetime.now(timezone.utc)
    user.created_at = _aware(user.created_at)
    db.commit()
    return user


@router.get("/{history_type}")
def query_history(
    history_type: str = Path(..., description="类型：messages/movements/social/all"),
    since: str | None = None,
    until: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    x_token: str = Header(..., alias="X-Token"),
    db=Depends(get_db),
):
    """分页查询历史数据（主查询接口）。"""
    if history_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"无效类型，可用：{VALID_TYPES}")

    user = _get_user(x_token, db)
    limit = min(limit, 200)

    now = datetime.now(timezone.utc)
    since_dt = None
    until_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="since 格式错误，请使用 ISO8601")
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="until 格式错误，请使用 ISO8601")

    result: list[dict] = []

    if history_type in ("messages", "all"):
        q = db.query(Message).filter(Message.to_id == user.id)
        if since_dt:
            q = q.filter(Message.created_at >= since_dt)
        if until_dt:
            q = q.filter(Message.created_at <= until_dt)
        if cursor:
            q = q.filter(Message.id < int(cursor))
        msgs = q.order_by(Message.id.desc()).limit(limit).all()

        from_ids = [m.from_id for m in msgs if m.from_id]
        name_map = {}
        if from_ids:
            rows = db.query(User.id, User.name).filter(User.id.in_(from_ids)).all()
            name_map = {uid: name for uid, name in rows}

        for m in msgs:
            result.append({
                "type": "message",
                "id": m.id,
                "from_id": m.from_id,
                "from_name": name_map.get(m.from_id, "unknown"),
                "content": m.content,
                "msg_type": m.msg_type,
                "ts": m.created_at.isoformat(),
                "read": m.read_at is not None,
            })

    if history_type in ("movements", "all"):
        q = db.query(MovementEvent).filter(MovementEvent.user_id == user.id)
        if since_dt:
            q = q.filter(MovementEvent.created_at >= since_dt)
        if until_dt:
            q = q.filter(MovementEvent.created_at <= until_dt)
        if cursor:
            q = q.filter(MovementEvent.id < int(cursor))
        moves = q.order_by(MovementEvent.id.desc()).limit(limit).all()
        for m in moves:
            result.append({
                "type": "movement",
                "id": m.id,
                "x": m.x,
                "y": m.y,
                "ts": m.created_at.isoformat(),
            })

    if history_type in ("social", "all"):
        q = db.query(SocialEvent).filter(SocialEvent.user_id == user.id)
        if since_dt:
            q = q.filter(SocialEvent.created_at >= since_dt)
        if until_dt:
            q = q.filter(SocialEvent.created_at <= until_dt)
        if cursor:
            q = q.filter(SocialEvent.id < int(cursor))
        events = q.order_by(SocialEvent.id.desc()).limit(limit).all()

        other_ids = [e.other_user_id for e in events if e.other_user_id]
        name_map = {}
        if other_ids:
            rows = db.query(User.id, User.name).filter(User.id.in_(other_ids)).all()
            name_map = {uid: name for uid, name in rows}

        for e in events:
            result.append({
                "type": e.event_type,
                "id": e.id,
                "other_user_id": e.other_user_id,
                "other_user_name": name_map.get(e.other_user_id, "unknown") if e.other_user_id else None,
                "x": e.x,
                "y": e.y,
                "ts": e.created_at.isoformat(),
            })

    result.sort(key=lambda x: x.get("ts", ""), reverse=True)
    result = result[:limit]

    has_more = len(result) == limit
    next_cursor = str(result[-1]["id"]) if result and has_more else None

    return {
        "type": history_type,
        "data": result,
        "pagination": {
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    }


@router.get("/backup")
def backup_history(
    type: str = "all",
    since: str | None = None,
    until: str | None = None,
    x_token: str = Header(..., alias="X-Token"),
    db=Depends(get_db),
):
    """全量备份查询（用于 AI Agent 本地数据丢失时恢复）。"""
    if type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"无效类型，可用：{VALID_TYPES}")

    user = _get_user(x_token, db)
    now = datetime.now(timezone.utc)

    # SQLite stores naive datetimes; keep comparisons naive to avoid type mismatch
    since_dt = user.created_at  # already normalized to naive by _get_user
    until_dt = now
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="since 格式错误")
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="until 格式错误")

    data: list[dict] = []

    if type in ("messages", "all"):
        msgs = db.query(Message).filter(
            Message.to_id == user.id,
            Message.created_at >= since_dt,
            Message.created_at <= until_dt,
        ).order_by(Message.created_at.asc()).all()

        from_ids = list({m.from_id for m in msgs if m.from_id})
        name_map = {}
        if from_ids:
            rows = db.query(User.id, User.name).filter(User.id.in_(from_ids)).all()
            name_map = {uid: name for uid, name in rows}

        for m in msgs:
            data.append({
                "type": "message",
                "id": m.id,
                "from_id": m.from_id,
                "from_name": name_map.get(m.from_id, "unknown"),
                "content": m.content,
                "msg_type": m.msg_type,
                "ts": m.created_at.isoformat(),
                "read": m.read_at is not None,
            })

    if type in ("movements", "all"):
        moves = db.query(MovementEvent).filter(
            MovementEvent.user_id == user.id,
            MovementEvent.created_at >= since_dt,
            MovementEvent.created_at <= until_dt,
        ).order_by(MovementEvent.created_at.asc()).all()
        for m in moves:
            data.append({
                "type": "movement",
                "id": m.id,
                "x": m.x,
                "y": m.y,
                "ts": m.created_at.isoformat(),
            })

    if type in ("social", "all"):
        events = db.query(SocialEvent).filter(
            SocialEvent.user_id == user.id,
            SocialEvent.created_at >= since_dt,
            SocialEvent.created_at <= until_dt,
        ).order_by(SocialEvent.created_at.asc()).all()

        other_ids = list({e.other_user_id for e in events if e.other_user_id})
        name_map = {}
        if other_ids:
            rows = db.query(User.id, User.name).filter(User.id.in_(other_ids)).all()
            name_map = {uid: name for uid, name in rows}

        for e in events:
            data.append({
                "type": e.event_type,
                "id": e.id,
                "other_user_id": e.other_user_id,
                "other_user_name": name_map.get(e.other_user_id, "unknown") if e.other_user_id else None,
                "x": e.x,
                "y": e.y,
                "ts": e.created_at.isoformat(),
            })

    data.sort(key=lambda x: x.get("ts", ""))

    return {
        "type": type,
        "data": data,
        "total": len(data),
        "since": since_dt.isoformat(),
        "until": until_dt.isoformat(),
    }
