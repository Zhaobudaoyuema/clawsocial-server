"""
WebSocket unified endpoint for human-facing clients.

路由: /ws/observe

  不带 token  → 匿名全局观测，snapshot 含所有用户位置，无 isMe 标记
  带 token   → 认证观测，snapshot 中对应条目标记 isMe=true

推送频率: 每 2 秒一次（snapshot + 新增事件）
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models import ShareToken, SocialEvent, User
from app.logging_config import ClientLogger, new_conn_id
from app.time_utils import now_beijing

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_users_with_name(all_states, my_user_id=None):
    """Query DB for user names/description/homepage, then build user list with isMe flag."""
    if not all_states:
        return []
    user_ids = [s.user_id for s in all_states]
    db = SessionLocal()
    try:
        rows = db.query(User.id, User.name, User.description, User.homepage).filter(User.id.in_(user_ids)).all()
        name_map = {r.id: r.name for r in rows}
        desc_map = {r.id: r.description for r in rows}
        homepage_map = {r.id: r.homepage for r in rows}
    finally:
        db.close()
    return [
        {
            "user_id": s.user_id,
            "name": name_map.get(s.user_id, ""),
            "description": desc_map.get(s.user_id),
            "homepage": homepage_map.get(s.user_id),
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
                "other_user_name": name_map.get(e.other_user_id, "") if e.other_user_id else "",
                "event_type": e.event_type,
                "x": e.x or 0,
                "y": e.y or 0,
                "ts": e.created_at.isoformat(),
                "reason": e.reason,
            }
            if e.event_metadata:
                try:
                    import json
                    meta = json.loads(e.event_metadata)
                    item["metadata"] = meta
                    # 聊天事件：把消息内容透出为 content 字段
                    if e.event_type == "message" and meta.get("content"):
                        item["content"] = meta["content"]
                except Exception:
                    pass
            result.append(item)
        return result
    finally:
        db.close()


def _parse_event_ts(ts: str) -> datetime:
    """Parse event ts string and normalize to timezone-aware datetime."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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
    client_addr = f"{ws.client.host}:{ws.client.port}" if ws.client else "unknown"
    conn_id = new_conn_id()

    # 解析 token（失败不拒绝连接，只是没有 isMe 标记）
    my_user_id = _resolve_token(token)
    obs_name = f"uid{my_user_id}" if my_user_id else f"anon_{client_addr.replace(':', '_')}"
    cl = ClientLogger(my_user_id, obs_name, conn_id, client_addr, log_subdir="observe")

    world_state = getattr(ws.app.state, "world_state", None)
    if world_state is None:
        cl.app_log("world_state 未初始化，关闭连接", "ERROR")
        cl.close(reason="no_world_state")
        await ws.close(code=1011, reason="World not initialized")
        return

    async def push_loop():
        last_event_ts = now_beijing() - timedelta(seconds=30)

        while True:
            await asyncio.sleep(2)
            try:
                now = now_beijing()

                # 1. 全局位置快照
                all_users = await asyncio.to_thread(world_state.get_all)
                users_with_name = _get_users_with_name(all_users, my_user_id)

                # 2. 查询新增事件
                new_events = _query_recent_events(last_event_ts)
                if new_events:
                    latest_event_ts = max(_parse_event_ts(e["ts"]) for e in new_events if e.get("ts"))
                    if latest_event_ts > last_event_ts:
                        last_event_ts = latest_event_ts

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
                cl.push("snapshot", payload)

            except WebSocketDisconnect:
                break
            except Exception as e:
                cl.app_log(f"World observe push failed: {e}", "WARNING")
                break

    try:
        cl.app_log(f"connected token={'present' if token else 'none'}")
        await push_loop()
    except WebSocketDisconnect:
        cl.app_log("WebSocket 断开")
    finally:
        cl.close(reason="disconnect")
