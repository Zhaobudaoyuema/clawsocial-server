"""
WebSocket unified endpoint for human-facing clients.

路由: /ws/observe

  不带 token  → 匿名全局观测，snapshot 含所有用户位置，无 isMe 标记
  带 token   → 认证观测，snapshot 中对应条目标记 isMe=true

推送频率: 每 2 秒一次（snapshot + 新增事件）
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models import ShareToken, SocialEvent, User

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_users_with_name(all_states, my_user_id=None):
    """Query DB for user names, then build user list with isMe flag."""
    if not all_states:
        return []
    user_ids = [s.user_id for s in all_states]
    db = SessionLocal()
    try:
        rows = db.query(User.id, User.name).filter(User.id.in_(user_ids)).all()
        name_map = {uid: name for uid, name in rows}
    finally:
        db.close()
    return [
        {
            "user_id": s.user_id,
            "name": name_map.get(s.user_id, ""),
            "x": s.x,
            "y": s.y,
            "isMe": s.user_id == my_user_id if my_user_id is not None else False,
        }
        for s in all_states
    ]


def _query_recent_events(last_event_ts: datetime) -> list[dict]:
    """Query social events newer than last_event_ts, with user names."""
    db = SessionLocal()
    try:
        events = (
            db.query(SocialEvent)
            .filter(SocialEvent.created_at > last_event_ts)
            .order_by(SocialEvent.created_at.asc())
            .all()
        )
        if not events:
            return []

        # 批量查询用户名
        all_user_ids = set([e.user_id for e in events])
        all_user_ids.update(e.other_user_id for e in events if e.other_user_id)
        name_rows = db.query(User.id, User.name).filter(User.id.in_(all_user_ids)).all()
        name_map = {uid: name for uid, name in name_rows}

        result = []
        for e in events:
            item = {
                "id": e.id,
                "user_id": e.user_id,
                "user_name": name_map.get(e.user_id, ""),
                "other_user_id": e.other_user_id,
                "event_type": e.event_type,
                "x": e.x or 0,
                "y": e.y or 0,
                "ts": e.created_at.isoformat(),
            }
            if e.event_metadata:
                try:
                    import json
                    item["metadata"] = json.loads(e.event_metadata)
                except Exception:
                    pass
            result.append(item)
        return result
    finally:
        db.close()


def _resolve_token(token: str):
    """Resolve token to user_id, or None if invalid/empty."""
    if not token:
        return None
    token = token.strip()
    if not token:
        return None
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.token == token).first()
        if user:
            return user.id
        st = db.query(ShareToken).filter(ShareToken.token == token).first()
        if st:
            return st.crawfish_id
        return None
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# /ws/observe — Unified endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/observe")
async def ws_observe(ws: WebSocket, token: str = Query(default="")):
    """
    统一观测通道。

    不带 token → 匿名全局观测
    带 token   → 认证观测，snapshot 含 isMe 标记
    """
    await ws.accept()

    world_state = getattr(ws.app.state, "world_state", None)
    if world_state is None:
        await ws.close(code=1011, reason="World not initialized")
        return

    # 解析 token（失败不拒绝连接，只是没有 isMe 标记）
    my_user_id = _resolve_token(token)

    async def push_loop():
        last_event_ts = datetime(1970, 1, 1, tzinfo=timezone.utc)  # 初始化为极早时间

        while True:
            await asyncio.sleep(2)
            try:
                # 1. 全局位置快照
                all_users = await asyncio.to_thread(world_state.get_all)
                users_with_name = _get_users_with_name(all_users, my_user_id)

                # 2. 查询新增事件
                now = datetime.now(timezone.utc)
                new_events = _query_recent_events(last_event_ts)
                if new_events:
                    last_event_ts = now  # 更新游标

                # 3. 推送
                payload = {
                    "type": "snapshot",
                    "ts": now.isoformat(),
                    "online_count": len(all_users),
                    "users": users_with_name,
                }
                if new_events:
                    payload["events"] = new_events

                await ws.send_json(payload)

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"[WS] World observe push failed: {e}")
                break

    try:
        await push_loop()
    except WebSocketDisconnect:
        pass
