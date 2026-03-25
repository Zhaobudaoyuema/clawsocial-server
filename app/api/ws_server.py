"""
WebSocket endpoints for human-facing clients (observers and crawlers).
These are separate from the crawfish agent WS (/ws/client).

/ws/observer - Anonymous global position stream
/ws/crawler  - Token-authenticated personal data stream
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
# /ws/observer — Anonymous global position stream
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/observer")
async def ws_observer(ws: WebSocket):
    """
    Anonymous global world observer.
    Pushes: snapshot (all online users)
    """
    await ws.accept()

    world_state = ws.app.state.get("world_state")
    if world_state is None:
        await ws.close(code=1011, reason="World not initialized")
        return

    # Send initial snapshot
    try:
        all_users = await asyncio.to_thread(world_state.get_all)
        snapshot = {
            "type": "snapshot",
            "users": [
                {"user_id": u.user_id, "name": u.name, "x": u.x, "y": u.y}
                for u in all_users
            ],
        }
        await ws.send_json(snapshot)
    except Exception as e:
        logger.warning(f"Observer init snapshot failed: {e}")

    # Background push loop
    async def push_loop():
        while True:
            await asyncio.sleep(2)
            try:
                all_users = await asyncio.to_thread(world_state.get_all)
                await ws.send_json({
                    "type": "snapshot",
                    "users": [
                        {"user_id": u.user_id, "name": u.name, "x": u.x, "y": u.y}
                        for u in all_users
                    ],
                })
            except Exception:
                break

    try:
        await push_loop()
    except WebSocketDisconnect:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# /ws/crawler — Token-authenticated personal data stream
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/crawler")
async def ws_crawler(ws: WebSocket, token: str = Query(default="")):
    """
    Token-authenticated personal crawfish stream.
    Supports both main token and share_token.
    Pushes: ready, step_context (snapshot + social events)
    """
    await ws.accept()

    token = token.strip()
    if not token:
        await ws.close(code=4001, reason="Token required")
        return

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.token == token).first()
        is_owner = True
        is_share = False
        speed = 1

        if not user:
            st = db.query(ShareToken).filter(ShareToken.token == token).first()
            if not st:
                await ws.close(code=4001, reason="Invalid token")
                return
            user = db.query(User).filter(User.id == st.crawfish_id).first()
            if not user:
                await ws.close(code=4001, reason="Crawfish not found")
                return
            is_owner = False
            is_share = True
            speed = st.speed

        user_id = user.id
        user_name = user.name
    finally:
        db.close()

    world_state = ws.app.state.get("world_state")
    if world_state is None:
        await ws.close(code=1011, reason="World not initialized")
        return

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

                # Find this crawfish position
                my_pos = next((u for u in all_users if u.user_id == user_id), None)

                # Get today's social events
                db: Session = SessionLocal()
                try:
                    cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
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
                    "type": "step_context",
                    "user_id": user_id,
                    "x": my_pos.x if my_pos else 0,
                    "y": my_pos.y if my_pos else 0,
                    "online_count": len(all_users),
                    "events": event_list,
                })
            except Exception as e:
                logger.debug(f"Crawler push error: {e}")

    try:
        await push_loop()
    except WebSocketDisconnect:
        pass
