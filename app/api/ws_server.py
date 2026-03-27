"""
WebSocket unified endpoint for human-facing clients.

/ws/observe           → world mode (anonymous, public)
/ws/observe?type=world→ world mode (explicit)
/ws/observe?type=crawler&token=xxx → personal mode (auth required)
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

def _get_users_with_name(all_states):
    """Query DB for user names, then build user list with name attached."""
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
        {"user_id": s.user_id, "name": name_map.get(s.user_id, ""), "x": s.x, "y": s.y}
        for s in all_states
    ]


def _auth_by_token(token: str, db):
    """
    Resolve a token to a (user_id, user_name, is_owner, is_share, speed) tuple.
    Returns None if the token is invalid.
    """
    user = db.query(User).filter(User.token == token).first()
    if user:
        return (user.id, user.name, True, False, 1)

    st = db.query(ShareToken).filter(ShareToken.token == token).first()
    if not st:
        return None
    user = db.query(User).filter(User.id == st.crawfish_id).first()
    if not user:
        return None
    return (user.id, user.name, False, True, st.speed)


# ─────────────────────────────────────────────────────────────────────────────
# /ws/observe — Unified endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/observe")
async def ws_observe(
    ws: WebSocket,
    type: str = Query(default="world"),
    token: str = Query(default=""),
):
    """
    Unified WebSocket endpoint.

    World mode (type=world, default):
        Anonymous global world snapshot. No auth required.
        Pushes every 2 seconds:
            {"type":"snapshot", "ts":"...", "online_count":N, "users":[...]}

    Crawler mode (type=crawler):
        Token-authenticated personal crawfish stream.
        Pushes every 5 seconds:
            {"type":"crawler", "ts":"...", "user_id":N, "x":N, "y":N,
             "online_count":N, "events":[...]}
    """
    await ws.accept()

    world_state = ws.app.state.get("world_state")
    if world_state is None:
        await ws.close(code=1011, reason="World not initialized")
        return

    # ── World mode ──────────────────────────────────────────────────────────
    if type == "world":

        async def push_loop():
            while True:
                await asyncio.sleep(2)
                try:
                    all_users = await asyncio.to_thread(world_state.get_all)
                    users_with_name = _get_users_with_name(all_users)
                    await ws.send_json({
                        "type": "snapshot",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "online_count": len(all_users),
                        "users": users_with_name,
                    })
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.warning(f"World observe push failed: {e}")
                    break

        try:
            await push_loop()
        except WebSocketDisconnect:
            pass
        return

    # ── Crawler mode ────────────────────────────────────────────────────────
    if type == "crawler":
        token = token.strip()
        if not token:
            await ws.close(code=4001, reason="Token required")
            return

        db = SessionLocal()
        try:
            auth = _auth_by_token(token, db)
            if auth is None:
                await ws.close(code=4001, reason="Invalid token")
                return
            user_id, user_name, is_owner, is_share, speed = auth
        finally:
            db.close()

        await ws.send_json({
            "type": "ready",
            "user": {"id": user_id, "name": user_name},
            "is_owner": is_owner,
            "is_share": is_share,
        })

        async def push_loop():
            while True:
                await asyncio.sleep(5)
                try:
                    all_users = await asyncio.to_thread(world_state.get_all)
                    my_pos = next((u for u in all_users if u.user_id == user_id), None)

                    db: Session = SessionLocal()
                    try:
                        cutoff = datetime.now(timezone.utc).replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        events = (
                            db.query(SocialEvent)
                            .filter(
                                SocialEvent.user_id == user_id,
                                SocialEvent.created_at >= cutoff,
                            )
                            .order_by(SocialEvent.created_at.desc())
                            .limit(20)
                            .all()
                        )
                        event_list = [
                            {
                                "type": e.event_type,
                                "other_user_id": e.other_user_id,
                                "x": e.x,
                                "y": e.y,
                                "ts": e.created_at.isoformat(),
                            }
                            for e in events
                        ]
                    finally:
                        db.close()

                    await ws.send_json({
                        "type": "crawler",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "user_id": user_id,
                        "x": my_pos.x if my_pos else 0,
                        "y": my_pos.y if my_pos else 0,
                        "online_count": len(all_users),
                        "events": event_list,
                    })
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.debug(f"Crawler observe push error: {e}")

        try:
            await push_loop()
        except WebSocketDisconnect:
            pass
        return

    # Unknown type — reject gracefully
    await ws.close(code=4002, reason="Unknown type")
