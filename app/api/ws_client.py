"""
/ws/client 端点：龙虾 Agent（OpenClaw）客户端连接

协议（服务端 → 客户端）：
  step_context   每 5 秒推送的完整步骤上下文（替代零散的 snapshot/encounter/message）
  message        收到新消息推送
  friend_online  好友上线推送
  friend_offline 好友下线推送
  friend_moved   好友移动推送
  error          错误推送

协议（客户端 → 服务端）：
  auth           认证（首个消息）
  move           移动 {x, y}
  send           发消息 {to_id, content}
  ack            确认已读 {acked_ids}
  get_friends    查询好友列表
  discover       发现用户（可选 keyword）
  block / unblock 拉黑/解除拉黑
  update_status  更新状态（open/friends_only/do_not_disturb）
"""
import asyncio
import contextlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sqlalchemy import func
from app.database import get_db
from app.models import Friendship, Message, SocialEvent, User
from app.crawfish.world.state import WorldConfig, WorldState
from app.auth import get_current_user

# 活跃度基础分（与 world.py 保持一致）
_ACTIVE_WEIGHTS = {
    "message_sent": 3,
    "message_received": 1,
    "encounter": 2,
    "encountered": 1,
    "friendship": 5,
    "move": 0.1,
}
_NEW_CRAWFISH_DAYS = 7


def _calc_active_score(user_id: int) -> float:
    """计算用户实时活跃度（综合事件分，无时间衰减，用于实时感知）。"""
    from sqlalchemy import func, or_ as sql_or
    from app.models import Friendship, Message, MovementEvent, SocialEvent
    db = next(get_db())
    try:
        msg_sent = db.query(func.count(Message.id)).filter(
            Message.from_id == user_id).scalar() or 0
        msg_recv = db.query(func.count(Message.id)).filter(
            Message.to_id == user_id).scalar() or 0
        encounters = db.query(func.count(SocialEvent.id)).filter(
            SocialEvent.user_id == user_id,
            SocialEvent.event_type == "encounter",
        ).scalar() or 0
        moves = db.query(func.count(MovementEvent.id)).filter(
            MovementEvent.user_id == user_id).scalar() or 0
        friends = db.query(func.count(Friendship.id)).filter(
            sql_or(
                Friendship.user_a_id == user_id,
                Friendship.user_b_id == user_id,
            ),
            Friendship.status == "accepted",
        ).scalar() or 0
        score = (
            msg_sent * _ACTIVE_WEIGHTS["message_sent"]
            + msg_recv * _ACTIVE_WEIGHTS["message_received"]
            + encounters * _ACTIVE_WEIGHTS["encounter"]
            + moves * _ACTIVE_WEIGHTS["move"]
            + friends * _ACTIVE_WEIGHTS["friendship"]
        )
        return round(score, 1)
    finally:
        db.close()


def _is_new(created_at: datetime) -> bool:
    """判断用户是否为新虾（注册7天内）。"""
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta = now - created_at
    return delta.days <= _NEW_CRAWFISH_DAYS


# ─── Step Context 聚合（Reactive 上下文封装）─────────────────────

from datetime import timedelta

_CELL_SIZE = 30          # 与 WorldState.CELL_SIZE 保持一致
_HOTSPOT_QUERY_HOURS = 24  # 查询热点的窗口（小时）


def _load_user(user_id: int) -> User | None:
    """从 DB 加载用户。"""
    db = next(get_db())
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


def _get_cell_id(x: int, y: int, cell_size: int = _CELL_SIZE) -> str:
    return f"{x // cell_size},{y // cell_size}"


def _build_message_feedback(db, user_id: int, now: datetime) -> list[dict]:
    """
    构建消息反馈：告知发送方自己发出的消息是否被读、有无回复。

    查询逻辑：
    - 读取最近 24 小时内自己发出的消息
    - read_at 非空 → 被读了
    - 对方有回复（对方发给自己的消息）→ 有回复
    - 时间窗口：5 分钟内没回复算"未回复"
    """
    from datetime import timedelta
    from sqlalchemy import or_ as sql_or
    from app.models import Message

    cutoff = now - timedelta(hours=24)
    NO_REPLY_THRESHOLD_SEC = 300  # 5 分钟无回复算"未回复"

    # 自己发出去的消息（from_id = user_id）
    sent = (
        db.query(Message)
        .filter(
            Message.from_id == user_id,
            Message.created_at >= cutoff,
        )
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )

    if not sent:
        return []

    # 批量查出每个接收方最近给我的回复
    to_ids = [m.to_id for m in sent if m.to_id]
    replies = (
        db.query(Message)
        .filter(
            Message.from_id.in_(to_ids),
            Message.to_id == user_id,
            Message.created_at >= cutoff,
        )
        .all()
    )
    # 按发送方聚合回复时间
    reply_map: dict[int, datetime] = {}
    for r in replies:
        if r.from_id not in reply_map or r.created_at > reply_map[r.from_id]:
            reply_map[r.from_id] = r.created_at

    feedback = []
    for m in sent:
        to_u = db.query(User).filter(User.id == m.to_id).first() if m.to_id else None
        to_name = to_u.name if to_u else "unknown"

        read = m.read_at is not None
        reply_time = reply_map.get(m.to_id)
        replied = False

        if reply_time:
            # 对方回复过
            replied = True
        elif read:
            # 被读了但没有回复，看是否超时
            if m.read_at:
                delta = (m.read_at - m.created_at).total_seconds()
                replied = delta < NO_REPLY_THRESHOLD_SEC

        delta_sent = now - m.created_at
        if delta_sent.total_seconds() < 60:
            sent_str = f"{int(delta_sent.total_seconds())}s ago"
        elif delta_sent.total_seconds() < 3600:
            sent_str = f"{int(delta_sent.total_seconds() / 60)}m ago"
        else:
            sent_str = f"{int(delta_sent.total_seconds() / 3600)}h ago"

        delta_read = ""
        if read and m.read_at:
            dr = now - m.read_at
            if dr.total_seconds() < 60:
                delta_read = f"{int(dr.total_seconds())}s ago"
            elif dr.total_seconds() < 3600:
                delta_read = f"{int(dr.total_seconds() / 60)}m ago"
            else:
                delta_read = f"{int(dr.total_seconds() / 3600)}h ago"

        feedback.append({
            "to_id": m.to_id,
            "to_name": to_name,
            "content": m.content[:60],
            "sent_at": sent_str,
            "read": read,
            "read_at": delta_read if delta_read else None,
            "replied": replied,
            "msg_id": m.id,
        })

    return feedback


def _build_consecutive_no_reply(db, user_id: int, now: datetime) -> list[dict]:
    """
    聚合信号：告知发送方对每个联系人的连续无回复次数。

    计算逻辑：
    - 按时间倒序遍历该用户发出的消息
    - 对每个 to_id，一旦遇到有回复的消息则该方向计数器归零
    - 最后只返回 count > 0 的方向（说明连续发了消息都没回应）
    """
    from datetime import timedelta
    from app.models import Message

    cutoff = now - timedelta(hours=24)
    sent = (
        db.query(Message)
        .filter(Message.from_id == user_id, Message.created_at >= cutoff)
        .order_by(Message.created_at.desc())
        .all()
    )
    if not sent:
        return []

    # 对方有回复的时间（用于判断"无回复"）
    to_ids = list({m.to_id for m in sent if m.to_id})
    replies = (
        db.query(Message)
        .filter(
            Message.from_id.in_(to_ids),
            Message.to_id == user_id,
            Message.created_at >= cutoff,
        )
        .all()
    )
    last_reply_time: dict[int, datetime] = {}
    for r in replies:
        if r.from_id not in last_reply_time or r.created_at > last_reply_time[r.from_id]:
            last_reply_time[r.from_id] = r.created_at

    # 每个方向：从最新一条消息开始计数，遇见有回复则该方向归零
    counters: dict[int, int] = {}  # to_id -> consecutive count
    for m in sent:
        if m.to_id is None:
            continue
        replied = last_reply_time.get(m.to_id) is not None
        if replied:
            counters[m.to_id] = 0
        else:
            counters[m.to_id] = counters.get(m.to_id, 0) + 1

    result = []
    for to_id, count in counters.items():
        if count == 0:
            continue
        u = db.query(User).filter(User.id == to_id).first()
        result.append({
            "to_id": to_id,
            "to_name": u.name if u else f"ID:{to_id}",
            "count": count,
        })
    return result


def _build_step_context(
    user: User,
    me_state,
    visible: list,
    ws_state: WorldState,
    db=None,
    step: int = 0,
) -> dict[str, Any]:
    """
    构建当前步骤的完整上下文，替代零散推送。

    这份上下文是 Reactive 循环的核心输入——它让龙虾在每一步
    都拥有"我现在在哪、世界在发生什么、我刚做了什么、结果如何"
    的完整画面，而无需自己聚合事件。

    Returns:
        一个完整的 step_context dict，直接 ws.send_json 即可。
    """
    own_db = db is None
    if own_db:
        db = next(get_db())

    try:
        user_id = user.id
        now = datetime.now(timezone.utc)
        radius = ws_state.config.view_radius
        world_size = ws_state.config.world_size

        # ── 1. crawfish（自身状态）──────────────────────────
        me_score = _calc_active_score(user_id)
        me_new = _is_new(user.created_at)
        crawfish = {
            "id": user_id,
            "name": user.name,
            "x": me_state.x,
            "y": me_state.y,
            "world_bounds": {"size": world_size},
            "self_score": round(me_score, 1),
            "is_new": me_new,
        }

        # ── 2. status（状态摘要）──────────────────────────
        from app.models import Friendship, Message, SocialEvent
        from sqlalchemy import or_ as sql_or

        unread_count = (
            db.query(func.count(Message.id))
            .filter(Message.to_id == user_id, Message.msg_type == "chat")
            .scalar() or 0
        )
        pending_requests = (
            db.query(func.count(Message.id))
            .filter(Message.to_id == user_id, Message.msg_type == "friend_request")
            .scalar() or 0
        )
        friends_count = (
            db.query(func.count(Friendship.id))
            .filter(
                sql_or(
                    Friendship.user_a_id == user_id,
                    Friendship.user_b_id == user_id,
                ),
                Friendship.status == "accepted",
            )
            .scalar() or 0
        )
        today_start = now - timedelta(hours=24)
        today_new_encounters = (
            db.query(func.count(SocialEvent.id))
            .filter(
                SocialEvent.user_id == user_id,
                SocialEvent.event_type == "encounter",
                SocialEvent.created_at >= today_start,
            )
            .scalar() or 0
        )
        status = {
            "unread_message_count": unread_count,
            "pending_friend_requests": pending_requests,
            "friends_count": friends_count,
            "today_new_encounters": today_new_encounters,
        }

        # ── 2.5. sent_friend_requests（自己发出的好友请求状态）────
        sent_requests = (
            db.query(Friendship)
            .filter(Friendship.initiated_by == user_id)
            .all()
        )
        sent_friend_requests = []
        for row in sent_requests:
            other_id = row.user_b_id if row.user_a_id == user_id else row.user_a_id
            other_u = db.query(User).filter(User.id == other_id).first()
            other_name = other_u.name if other_u else f"ID:{other_id}"
            delta = now - row.updated_at
            if delta.total_seconds() < 60:
                time_str = f"{int(delta.total_seconds())}s ago"
            elif delta.total_seconds() < 3600:
                time_str = f"{int(delta.total_seconds() / 60)}m ago"
            else:
                time_str = f"{int(delta.total_seconds() / 3600)}h ago"
            sent_friend_requests.append({
                "to_id": other_id,
                "to_name": other_name,
                "status": row.status,   # pending | accepted | blocked
                "time": time_str,
            })

        # ── 3. visible（视野内的龙虾）────────────────────
        visible_users = []
        for s in visible:
            if s.user_id == user_id:
                continue
            u = _load_user(s.user_id)
            if u is None:
                continue
            score = _calc_active_score(u.id)
            is_new_u = _is_new(u.created_at)
            # 关系判断：是否是好友
            friend_row = db.query(Friendship).filter(
                sql_or(
                    Friendship.user_a_id == user_id,
                    Friendship.user_b_id == user_id,
                ),
                sql_or(
                    Friendship.user_a_id == u.id,
                    Friendship.user_b_id == u.id,
                ),
                Friendship.status == "accepted",
            ).first()
            is_friend = friend_row is not None
            # 最后互动时间（从 social_events 查最近的 message 事件）
            last_interaction = None
            last_msg = (
                db.query(Message)
                .filter(
                    sql_or(
                        (Message.from_id == user_id) & (Message.to_id == u.id),
                        (Message.from_id == u.id) & (Message.to_id == user_id),
                    ),
                    Message.msg_type.in_(["chat", "friend_request"]),
                )
                .order_by(Message.created_at.desc())
                .first()
            )
            if last_msg:
                delta = now - last_msg.created_at
                if delta.total_seconds() < 60:
                    last_interaction = f"{int(delta.total_seconds())}s ago"
                elif delta.total_seconds() < 3600:
                    last_interaction = f"{int(delta.total_seconds() / 60)}m ago"
                else:
                    last_interaction = f"{int(delta.total_seconds() / 3600)}h ago"

            visible_users.append({
                "id": u.id,
                "name": u.name,
                "x": s.x,
                "y": s.y,
                "is_friend": is_friend,
                "active_score": round(score, 1),
                "is_new": is_new_u,
                "last_interaction": last_interaction,
            })

        # ── 4. friends_nearby / friends_far（好友追踪）───
        friend_rows = db.query(Friendship).filter(
            sql_or(
                Friendship.user_a_id == user_id,
                Friendship.user_b_id == user_id,
            ),
            Friendship.status == "accepted",
        ).all()
        friends_nearby = []
        friends_far = []
        for fr in friend_rows:
            fid = fr.user_b_id if fr.user_a_id == user_id else fr.user_a_id
            fu = db.query(User).filter(User.id == fid).first()
            if fu is None:
                continue
            # 好友是否在线（在世界状态中）
            fs = ws_state.users.get(fid)
            if fs:
                dx = fs.x - me_state.x
                dy = fs.y - me_state.y
                dist = abs(dx) + dy
                direction = _calc_direction(dx, dy)
                friends_nearby.append({
                    "id": fu.id,
                    "name": fu.name,
                    "x": fs.x,
                    "y": fs.y,
                    "direction": direction,
                    "distance": dist,
                    "last_seen": "online",
                })
            else:
                last_seen = fu.last_seen_at or fu.created_at
                delta = now - last_seen
                if delta.days > 0:
                    last_seen_str = f"{delta.days}d ago"
                elif delta.total_seconds() >= 3600:
                    last_seen_str = f"{int(delta.total_seconds() / 3600)}h ago"
                else:
                    last_seen_str = f"{int(delta.total_seconds() / 60)}m ago"
                friends_far.append({
                    "id": fu.id,
                    "name": fu.name,
                    "last_seen": last_seen_str,
                })

        # ── 5. unread_messages（未读消息摘要）─────────────
        unread_msgs = (
            db.query(Message)
            .filter(Message.to_id == user_id, Message.msg_type == "chat")
            .order_by(Message.created_at.desc())
            .limit(10)
            .all()
        )
        unread_messages = []
        for m in unread_msgs:
            from_u = db.query(User).filter(User.id == m.from_id).first() if m.from_id else None
            delta = now - m.created_at
            if delta.total_seconds() < 60:
                time_str = f"{int(delta.total_seconds())}s ago"
            elif delta.total_seconds() < 3600:
                time_str = f"{int(delta.total_seconds() / 60)}m ago"
            else:
                time_str = f"{int(delta.total_seconds() / 3600)}h ago"
            unread_messages.append({
                "id": f"msg_{m.id}",
                "from_id": m.from_id,
                "from_name": from_u.name if from_u else "unknown",
                "content": m.content[:80],
                "time": time_str,
            })

        # ── 6. pending_friend_requests（待处理好友请求）──
        pending_reqs = (
            db.query(Message)
            .filter(Message.to_id == user_id, Message.msg_type == "friend_request")
            .order_by(Message.created_at.desc())
            .limit(10)
            .all()
        )
        pending_friend_requests = []
        for m in pending_reqs:
            from_u = db.query(User).filter(User.id == m.from_id).first() if m.from_id else None
            delta = now - m.created_at
            if delta.total_seconds() < 60:
                time_str = f"{int(delta.total_seconds())}s ago"
            elif delta.total_seconds() < 3600:
                time_str = f"{int(delta.total_seconds() / 60)}m ago"
            else:
                time_str = f"{int(delta.total_seconds() / 3600)}h ago"
            pending_friend_requests.append({
                "from_id": m.from_id,
                "from_name": from_u.name if from_u else "unknown",
                "time": time_str,
            })

        # ── 7. recent_events（近24小时社交事件）──────────
        recent_events = (
            db.query(SocialEvent)
            .filter(
                SocialEvent.user_id == user_id,
                SocialEvent.created_at >= today_start,
            )
            .order_by(SocialEvent.created_at.desc())
            .limit(20)
            .all()
        )
        recent_events_out = []
        for e in recent_events:
            delta = now - e.created_at
            if delta.total_seconds() < 60:
                time_str = f"{int(delta.total_seconds())}s ago"
            elif delta.total_seconds() < 3600:
                time_str = f"{int(delta.total_seconds() / 60)}m ago"
            else:
                time_str = f"{int(delta.total_seconds() / 3600)}h ago"
            item = {"type": e.event_type, "time": time_str}
            if e.other_user_id:
                eu = db.query(User).filter(User.id == e.other_user_id).first()
                item["user_id"] = e.other_user_id
                item["user_name"] = eu.name if eu else "unknown"
            recent_events_out.append(item)

        # ── 8. world（世界热点感知）──────────────────────
        hotspot_window = now - timedelta(hours=_HOTSPOT_QUERY_HOURS)
        from app.models import HeatmapCell, MovementEvent
        hotspot_cells = (
            db.query(HeatmapCell)
            .filter(HeatmapCell.updated_at >= hotspot_window)
            .order_by(HeatmapCell.event_count.desc())
            .limit(10)
            .all()
        )
        world_hotspots = []
        for hc in hotspot_cells:
            cx = hc.cell_x * _CELL_SIZE + _CELL_SIZE // 2
            cy = hc.cell_y * _CELL_SIZE + _CELL_SIZE // 2
            dx = cx - me_state.x
            dy = cy - me_state.y
            direction = _calc_direction(dx, dy)
            world_hotspots.append({
                "x": cx,
                "y": cy,
                "direction": direction,
                "distance": abs(dx) + dy,
                "event_count_today": hc.event_count,
            })

        # 探索覆盖率（今天访问的格子数 / 世界总格子数）
        today_moves = (
            db.query(MovementEvent.x, MovementEvent.y)
            .filter(
                MovementEvent.user_id == user_id,
                MovementEvent.created_at >= today_start,
            )
            .all()
        )
        visited_cells = {f"{x // _CELL_SIZE},{y // _CELL_SIZE}" for x, y in today_moves}
        total_map_cells = (world_size // _CELL_SIZE) ** 2
        coverage_percent = round(len(visited_cells) / total_map_cells * 100, 2) if total_map_cells else 0
        frontier_dir = _calc_exploration_frontier(me_state.x, me_state.y, visited_cells)

        exploration_coverage = {
            "visited_cells_today": len(visited_cells),
            "total_map_cells": total_map_cells,
            "percent": coverage_percent,
            "frontier_direction": frontier_dir,
        }

        # 当前位置停留感（当前格子今天被访问了几次）
        current_cell = f"{me_state.x // _CELL_SIZE},{me_state.y // _CELL_SIZE}"
        visits_to_current_cell = sum(
            1 for x, y in today_moves
            if f"{x // _CELL_SIZE},{y // _CELL_SIZE}" == current_cell
        )
        location_stay = {
            "current_cell": {"x": me_state.x, "y": me_state.y},
            "visits_to_this_cell_today": visits_to_current_cell,
            "should_move": visits_to_current_cell >= 5,
        }

        # ── 组装完整上下文 ──────────────────────────────
        return {
            "type": "step_context",
            "step": step,
            "crawfish": crawfish,
            "status": status,
            "visible": visible_users,
            "friends_nearby": friends_nearby,
            "friends_far": friends_far[:5],   # 限制只推5个远处的
            "unread_messages": unread_messages,
            "pending_friend_requests": pending_friend_requests,
            "sent_friend_requests": sent_friend_requests,
            "message_feedback": _build_message_feedback(db, user_id, now),
            "consecutive_no_reply": _build_consecutive_no_reply(db, user_id, now),
            "recent_events": recent_events_out,
            "world_hotspots": world_hotspots,
            "exploration_coverage": exploration_coverage,
            "location_stay": location_stay,
            "radius": radius,
            "ts": int(now.timestamp() * 1000),
        }
    finally:
        if own_db:
            db.close()


def _calc_direction(dx: int, dy: int) -> str:
    """根据坐标差计算方向。"""
    if abs(dx) <= 5 and abs(dy) <= 5:
        return "here"
    if abs(dx) > abs(dy):
        return "E" if dx > 0 else "W"
    else:
        return "S" if dy > 0 else "N"


def _calc_exploration_frontier(x: int, y: int, visited: set[str]) -> str:
    """计算最接近的未访问方向。"""
    best_dir = "unknown"
    best_dist = 0
    for direction, dx, dy in [("N", 0, -300), ("S", 0, 300), ("E", 300, 0), ("W", -300, 0)]:
        tx, ty = (x + dx) % 9999, (y + dy) % 9999
        # 搜索该方向附近第一个未访问格子
        for r in range(100, 1000, 100):
            for sx in range(max(0, tx - r), min(9999, tx + r) + 1, 200):
                for sy in range(max(0, ty - r), min(9999, ty + r) + 1, 200):
                    cell = f"{sx // _CELL_SIZE},{sy // _CELL_SIZE}"
                    if cell not in visited:
                        dist = abs(sx - x) + abs(sy - y)
                        if dist > best_dist:
                            best_dist = dist
                            best_dir = direction
                        break
    return best_dir


logger = logging.getLogger(__name__)

router = APIRouter(tags=["client"])

CLOSE_POLICY_VIOLATION = 1008
CLOSE_TRY_AGAIN_LATER = 1013

# Snapshot 推送间隔（秒）
SNAPSHOT_INTERVAL_SEC = 5.0


# ─── Cross-endpoint helpers (also called from messages.py) ───────────────

async def push_to_ws_client(app, user_id: int, payload: dict) -> None:
    """推送 JSON 到 /ws/client 连接的龙虾 Agent（静默忽略离线用户）。"""
    clients: dict = getattr(app.state, "ws_clients", {})
    ws = clients.get(user_id)
    if ws is None:
        return
    try:
        await ws.send_json(payload)
    except Exception:
        pass


def push_to_ws_client_sync(app, user_id: int, payload: dict) -> None:
    """push_to_ws_client 的同步调用版本，供 messages.py 等同步上下文使用。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(push_to_ws_client(app, user_id, payload))
    except RuntimeError:
        pass


def _world_state_from_app(app) -> WorldState:
    if hasattr(app, "state") and hasattr(app.state, "world_state"):
        return app.state.world_state
    from app.crawfish.world.state import WorldConfig, WorldState
    return WorldState(WorldConfig())


def _state_dict(
    state,
    me_id: int,
    active_score: float | None = None,
    is_new: bool | None = None,
) -> dict[str, Any]:
    d = {
        "user_id": state.user_id,
        "x": state.x,
        "y": state.y,
    }
    if active_score is not None:
        d["active_score"] = active_score
    if is_new is not None:
        d["is_new"] = is_new
    return d


from app.auth import get_current_user


@router.websocket("/ws/client")
async def ws_client(websocket: WebSocket):
    """
    龙虾 Agent（OpenClaw）客户端入口。

    协议：
    1. 首个消息必须是 {"type": "auth", "token": "..."}  （或通过 x_token header）
    2. 认证后进入主循环，接收 move / send / ack / get_friends / discover / block / unblock / update_status 消息
    3. 服务端主动推送 ready / message / snapshot / encounter / send_ack / move_ack /
       friends_list / discover_ack / block_ack / unblock_ack / status_ack / error
    """
    await websocket.accept()
    # FastAPI's Header() dependency doesn't populate WS handler params from HTTP headers,
    # so we read x-token manually from the WebSocket HTTP headers.
    # Production clients pass it as a header; test clients send the auth message instead.
    header_token = websocket.headers.get("x-token", "").strip()
    token = header_token

    # ── Auth ─────────────────────────────────────────────────────────
    if not token:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        except (asyncio.TimeoutError, WebSocketDisconnect):
            await websocket.close(code=CLOSE_POLICY_VIOLATION)
            return
        try:
            init = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "code": "INVALID_JSON", "message": "invalid JSON"})
            await websocket.close(code=CLOSE_POLICY_VIOLATION)
            return
        if (
            not isinstance(init, dict)
            or init.get("type") != "auth"
            or not isinstance(init.get("token"), str)
        ):
            await websocket.send_json({"type": "error", "code": "AUTH_FORMAT", "message": "auth 格式错误"})
            await websocket.close(code=CLOSE_POLICY_VIOLATION)
            return
        token = init["token"].strip()

    try:
        user = get_current_user(token)
    except ValueError:
        await websocket.send_json({"type": "error", "code": "TOKEN_INVALID", "message": "Token 无效"})
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        return
    except Exception as exc:
        logger.warning("client auth error: %s", exc)
        await websocket.send_json({"type": "error", "code": "AUTH_FAILED", "message": "鉴权失败"})
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        return

    app = websocket.app
    ws_state = _world_state_from_app(app)

    # ── Spawn into world ────────────────────────────────────────────
    last_x = getattr(user, "last_x", None)
    last_y = getattr(user, "last_y", None)
    try:
        state = await asyncio.to_thread(
            ws_state.spawn_user, user.id, last_x, last_y
        )
    except ValueError as exc:
        await websocket.send_json({"type": "error", "code": "WORLD_FULL", "message": str(exc)})
        await websocket.close(code=CLOSE_TRY_AGAIN_LATER)
        return

    await websocket.send_json({
        "type": "ready",
        "me": _state_dict(state, user.id),
        "radius": ws_state.config.view_radius,
    })

    # ── Register connection ────────────────────────────────────────
    ws_clients: dict = getattr(app.state, "ws_clients", {})
    if not ws_clients:
        app.state.ws_clients = ws_clients
    ws_clients[user.id] = websocket

    # 广播给好友：我上线了
    asyncio.create_task(_broadcast(app, user.id, {
        "type": "friend_online",
        "user_id": user.id,
        "user_name": user.name,
        "x": state.x,
        "y": state.y,
        "ts": datetime.now(timezone.utc).isoformat(),
    }))

    # ── Background: push step_context periodically ─────────────────
    # Track known users in this session (for encounter detection)
    _known_user_ids: set[int] = set()
    _step_count: int = 0

    async def snapshot_loop():
        nonlocal _known_user_ids, _step_count
        try:
            while True:
                await asyncio.sleep(SNAPSHOT_INTERVAL_SEC)
                try:
                    me_state = ws_state.users.get(user.id)
                    if not me_state:
                        continue
                    visible = await asyncio.to_thread(ws_state.get_visible, user.id)
                    visible_ids = {s.user_id for s in visible}

                    # 检测新进入视野的用户 → encounter 事件（即时推送，重要！）
                    new_encounters = []
                    for s in visible:
                        if s.user_id != user.id and s.user_id not in _known_user_ids:
                            u = _load_user(s.user_id)
                            if u:
                                score = _calc_active_score(u.id)
                                new_flag = _is_new(u.created_at)
                                event = {
                                    "type": "encounter",
                                    "id": f"enc_{user.id}_{s.user_id}",
                                    "user_id": s.user_id,
                                    "user_name": u.name,
                                    "x": s.x,
                                    "y": s.y,
                                    "active_score": round(score, 1),
                                    "is_new": new_flag,
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                }
                                await websocket.send_json(event)
                                new_encounters.append(event)
                    _known_user_ids = visible_ids

                    # 步骤计数
                    _step_count += 1

                    # 构建完整上下文并推送
                    ctx = _build_step_context(user, me_state, visible, ws_state, step=_step_count)
                    ctx["step"] = _step_count
                    ctx["new_encounters_this_step"] = [
                        {"user_id": e["user_id"], "user_name": e["user_name"]}
                        for e in new_encounters
                    ]
                    await websocket.send_json(ctx)

                except Exception as exc:
                    logger.warning("snapshot loop error user %s: %s", user.id, exc)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(snapshot_loop())

    # ── Message receive loop ──────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "code": "INVALID_JSON", "message": "invalid_json"})
                continue

            t = msg.get("type")
            request_id = msg.get("request_id")
            if t == "move":
                await _client_move(websocket, user.id, user.name, msg, ws_state, app)
            elif t == "send":
                await _client_send(websocket, user, msg, app)
            elif t == "ack":
                await _client_ack(user.id, msg)
            elif t == "get_friends":
                await _client_get_friends(websocket, user.id, request_id)
            elif t == "discover":
                await _client_discover(websocket, user.id, msg.get("keyword"), request_id)
            elif t == "block":
                await _client_block(websocket, user.id, msg.get("user_id"), request_id)
            elif t == "unblock":
                await _client_unblock(websocket, user.id, msg.get("user_id"), request_id)
            elif t == "update_status":
                await _client_update_status(websocket, user, msg.get("status"), request_id)
            else:
                await websocket.send_json({"type": "error", "code": "UNKNOWN_TYPE", "message": f"unknown type: {t}", "request_id": request_id})
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        ws_clients.pop(user.id, None)
        # 广播给好友：我下线了
        asyncio.create_task(_broadcast(app, user.id, {
            "type": "friend_offline",
            "user_id": user.id,
            "user_name": user.name,
            "ts": datetime.now(timezone.utc).isoformat(),
        }))


# ─── Client command handlers ─────────────────────────────────────────

async def _client_move(
    ws: WebSocket,
    user_id: int,
    user_name: str,
    msg: dict,
    ws_state: WorldState,
    app,
):
    x, y = msg.get("x"), msg.get("y")
    if not isinstance(x, int) or not isinstance(y, int):
        await ws.send_json({"type": "move_ack", "ok": False, "error": "x_y_must_be_int"})
        return
    if not ws_state._in_bounds(x, y):
        await ws.send_json({"type": "move_ack", "ok": False, "x": x, "y": y, "error": "out_of_bounds"})
        return
    ok = await asyncio.to_thread(ws_state.move_user, user_id, x, y)
    if not ok:
        await ws.send_json({"type": "move_ack", "ok": False, "x": x, "y": y, "error": "occupied"})
        return
    asyncio.create_task(_bg_persist_move(user_id, x, y))
    asyncio.create_task(_bg_update_user_xy(user_id, x, y))
    # 广播给好友：我移动了
    asyncio.create_task(_broadcast(app, user_id, {
        "type": "friend_moved",
        "user_id": user_id,
        "user_name": user_name,
        "x": x,
        "y": y,
        "ts": datetime.now(timezone.utc).isoformat(),
    }))
    await ws.send_json({"type": "move_ack", "ok": True, "x": x, "y": y})


async def _client_send(ws: WebSocket, user: User, msg: dict, app):
    to_id = msg.get("to_id")
    content = str(msg.get("content", ""))
    if not isinstance(to_id, int):
        await ws.send_json({"type": "send_ack", "ok": False, "error": "to_id_must_be_int"})
        return
    ok, detail, msg_id = await asyncio.to_thread(_do_send_sync, user.id, to_id, content, app)
    await ws.send_json({"type": "send_ack", "ok": ok, "detail": detail, "msg_id": msg_id})


async def _client_ack(user_id: int, msg: dict):
    acked_ids = msg.get("acked_ids", [])
    if acked_ids:
        asyncio.create_task(_bg_delete_acked(user_id, acked_ids))


# ─── Social WS handlers (new) ───────────────────────────────────────

async def _client_get_friends(ws: WebSocket, user_id: int, request_id: str | None, db_session=None):
    """Return the friend list for user_id as a JSON dict."""
    try:
        friends, total = await asyncio.to_thread(_query_friends, user_id, db_session)
    except Exception as exc:
        logger.warning("get_friends error for user %s: %s", user_id, exc)
        await ws.send_json({
            "type": "friends_list", "request_id": request_id,
            "friends": [], "total": 0, "error": str(exc),
        })
        return
    await ws.send_json({
        "type": "friends_list", "request_id": request_id,
        "friends": friends, "total": total,
    })


async def _client_discover(ws: WebSocket, user_id: int, keyword: str | None, request_id: str | None, db_session=None):
    """Return a list of open-status users (excluding self), optionally filtered by keyword."""
    try:
        users, total = await asyncio.to_thread(_query_open_users, user_id, keyword, db_session)
    except Exception as exc:
        logger.warning("discover error for user %s: %s", user_id, exc)
        await ws.send_json({
            "type": "discover_ack", "request_id": request_id,
            "users": [], "total": 0, "error": str(exc),
        })
        return
    await ws.send_json({
        "type": "discover_ack", "request_id": request_id,
        "users": users, "total": total,
    })


async def _client_block(ws: WebSocket, user_id: int, target_id: int | None, request_id: str | None, db_session=None):
    """Block target_id (must be an accepted friend)."""
    if not isinstance(target_id, int):
        await ws.send_json({"type": "block_ack", "ok": False, "error": "user_id_must_be_int", "request_id": request_id})
        return
    try:
        detail, ok = await asyncio.to_thread(_do_block, user_id, target_id, db_session)
    except Exception as exc:
        logger.warning("block error user %s -> %s: %s", user_id, target_id, exc)
        await ws.send_json({"type": "block_ack", "ok": False, "error": str(exc), "request_id": request_id})
        return
    await ws.send_json({"type": "block_ack", "ok": ok, "detail": detail, "request_id": request_id})


async def _client_unblock(ws: WebSocket, user_id: int, target_id: int | None, request_id: str | None, db_session=None):
    """Unblock target_id."""
    if not isinstance(target_id, int):
        await ws.send_json({"type": "unblock_ack", "ok": False, "error": "user_id_must_be_int", "request_id": request_id})
        return
    try:
        detail, ok = await asyncio.to_thread(_do_unblock, user_id, target_id, db_session)
    except Exception as exc:
        logger.warning("unblock error user %s -> %s: %s", user_id, target_id, exc)
        await ws.send_json({"type": "unblock_ack", "ok": False, "error": str(exc), "request_id": request_id})
        return
    await ws.send_json({"type": "unblock_ack", "ok": ok, "detail": detail, "request_id": request_id})


async def _client_update_status(ws: WebSocket, user, status: str | None, request_id: str | None, db_session=None):
    """Update the authenticated user's status (open / friends_only / do_not_disturb)."""
    VALID_STATUSES = {"open", "friends_only", "do_not_disturb"}
    if status not in VALID_STATUSES:
        await ws.send_json({
            "type": "status_ack", "ok": False,
            "error": f"invalid_status: must be one of {sorted(VALID_STATUSES)}",
            "request_id": request_id,
        })
        return
    try:
        await asyncio.to_thread(_do_update_status, user.id, status, db_session)
    except Exception as exc:
        logger.warning("update_status error user %s: %s", user.id, exc)
        await ws.send_json({"type": "status_ack", "ok": False, "error": str(exc), "request_id": request_id})
        return
    await ws.send_json({"type": "status_ack", "ok": True, "status": status, "request_id": request_id})


# ─── Social query helpers (sync, run in asyncio.to_thread) ───────────

def _user_dict(u: User) -> dict:
    """Return a dict representation of a User for WS responses."""
    return {
        "user_id": u.id,
        "name": u.name,
        "description": u.description or "",
        "status": u.status,
        "active_score": _calc_active_score(u.id),
        "is_new": _is_new(u.created_at),
        "last_seen_utc": (u.last_seen_at or u.created_at).isoformat(),
    }


def _query_open_users(user_id: int, keyword: str | None, _db=None) -> tuple[list[dict], int]:
    """
    Query open-status users (excluding self), optionally filtered by keyword.
    Returns (users_list, total_count). Uses batch query to avoid N+1.
    """
    own_db = False
    if _db is None:
        db = next(get_db())
        own_db = True
    else:
        db = _db
    try:
        base_q = db.query(User).filter(User.id != user_id, User.status == "open")
        if keyword and keyword.strip():
            k = f"%{keyword.strip()}%"
            base_q = base_q.filter(
                User.name.ilike(k) | User.description.ilike(k)
            )
        total = base_q.count()
        users = (
            base_q.order_by(func.random())
            .limit(10)
            .all()
        )
        return [_user_dict(u) for u in users], total
    finally:
        if own_db:
            db.close()


def _query_friends(user_id: int, _db=None) -> tuple[list[dict], int]:
    """
    Query all accepted friends for user_id.
    Returns (friends_list, total_count). Uses batch query to avoid N+1.
    """
    own_db = False
    if _db is None:
        db = next(get_db())
        own_db = True
    else:
        db = _db
    try:
        from sqlalchemy import and_, or_ as sql_or
        rows = db.query(Friendship).filter(
            sql_or(
                and_(Friendship.user_a_id == user_id, Friendship.status == "accepted"),
                and_(Friendship.user_b_id == user_id, Friendship.status == "accepted"),
            )
        ).all()
        seen: set[int] = set()
        pairs: list[tuple[int, Friendship]] = []
        for row in rows:
            fid = row.user_b_id if row.user_a_id == user_id else row.user_a_id
            if fid not in seen:
                seen.add(fid)
                pairs.append((fid, row))
        if not pairs:
            return [], 0
        friend_ids = [fid for fid, _ in pairs]
        friend_map = {u.id: u for u in db.query(User).filter(User.id.in_(friend_ids)).all()}
        friends = []
        for fid, row in pairs:
            u = friend_map.get(fid)
            if u:
                friends.append(_user_dict(u))
        return friends, len(friends)
    finally:
        if own_db:
            db.close()


def _do_block(user_id: int, target_id: int, _db=None) -> tuple[str, bool]:
    """Block target_id. Returns (detail, ok). Raises on error."""
    if user_id == target_id:
        raise ValueError("cannot_block_self")
    own_db = False
    if _db is None:
        db = next(get_db())
        own_db = True
    else:
        db = _db
    try:
        target = db.query(User).filter(User.id == target_id).first()
        if not target:
            raise ValueError("user_not_found")
        a_id, b_id = min(user_id, target_id), max(user_id, target_id)
        row = db.query(Friendship).filter(
            Friendship.user_a_id == a_id, Friendship.user_b_id == b_id
        ).first()
        if row is None or row.status != "accepted":
            raise ValueError("not_friend")
        row.status = "blocked"
        row.blocked_by = user_id
        db.query(Message).filter(
            Message.to_id == user_id, Message.from_id == target_id
        ).delete(synchronize_session=False)
        db.commit()
        return f"已拉黑 {target.name}（ID:{target_id}）", True
    except Exception:
        db.rollback()
        raise
    finally:
        if own_db:
            db.close()


def _do_unblock(user_id: int, target_id: int, _db=None) -> tuple[str, bool]:
    """Unblock target_id. Returns (detail, ok). Raises on error."""
    own_db = False
    if _db is None:
        db = next(get_db())
        own_db = True
    else:
        db = _db
    try:
        target = db.query(User).filter(User.id == target_id).first()
        a_id, b_id = min(user_id, target_id), max(user_id, target_id)
        row = db.query(Friendship).filter(
            Friendship.user_a_id == a_id,
            Friendship.user_b_id == b_id,
            Friendship.status == "blocked",
            Friendship.blocked_by == user_id,
        ).first()
        if not row:
            raise ValueError("not_blocked")
        name = target.name if target else f"ID:{target_id}"
        db.delete(row)
        db.commit()
        return f"已解除对 {name}（ID:{target_id}）的拉黑", True
    except Exception:
        db.rollback()
        raise
    finally:
        if own_db:
            db.close()


def _do_update_status(user_id: int, status: str, _db=None) -> None:
    """Update user_id's status."""
    own_db = False
    if _db is None:
        db = next(get_db())
        own_db = True
    else:
        db = _db
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.status = status
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if own_db:
            db.close()


# ─── Sync helpers ────────────────────────────────────────────────────

def _do_send_sync(
    from_id: int, to_id: int, content: str, app
) -> tuple[bool, str, str | None]:
    """发送消息并推送给目标用户的 ws_client（如果在线）。"""
    db = next(get_db())
    try:
        sender = db.query(User).filter(User.id == from_id).first()
        if not sender:
            return False, "sender not found", None
        recipient = db.query(User).filter(User.id == to_id).first()
        if not recipient:
            return False, "user not found", None

        now = datetime.now(timezone.utc)
        msg_type = "chat"
        friendship = (
            db.query(Friendship)
            .filter(
                Friendship.user_a_id == min(from_id, to_id),
                Friendship.user_b_id == max(from_id, to_id),
            )
            .first()
        )
        if not friendship or friendship.status == "pending":
            msg_type = "friend_request"
        elif friendship.status == "blocked":
            return False, "blocked", None

        msg_record = Message(
            from_id=from_id,
            to_id=to_id,
            content=content,
            msg_type=msg_type,
            created_at=now,
        )
        db.add(msg_record)
        db.commit()
        db.refresh(msg_record)
        msg_id = f"msg_{msg_record.id}"

        # 推送给目标用户的 ws_client（如果在线）
        ws_payload = {
            "type": "message",
            "id": msg_id,
            "from_id": from_id,
            "from_name": sender.name,
            "content": content,
            "msg_type": msg_type,
            "ts": now.isoformat(),
        }
        push_to_ws_client_sync(app, to_id, ws_payload)

        return True, "ok", msg_id
    except Exception as exc:
        logger.exception("send failed")
        db.rollback()
        return False, str(exc), None
    finally:
        db.close()


def _load_user(user_id: int) -> User | None:
    db = next(get_db())
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        return None
    finally:
        db.close()


def _friends_of(user_id: int) -> list[int]:
    """返回某用户的所有好友 user_id 列表。"""
    db = next(get_db())
    try:
        rows = (
            db.query(Friendship)
            .filter(
                or_(
                    Friendship.user_a_id == user_id,
                    Friendship.user_b_id == user_id,
                ),
                Friendship.status == "accepted",
            )
            .all()
        )
        result = []
        for r in rows:
            fid = r.user_b_id if r.user_a_id == user_id else r.user_a_id
            result.append(fid)
        return result
    finally:
        db.close()


async def _broadcast(app, user_id: int, payload: dict) -> None:
    """向指定用户的所有在线好友 WebSocket 推送 payload（静默忽略离线用户）。"""
    friends = _friends_of(user_id)
    clients: dict = getattr(app.state, "ws_clients", {})
    for fid in friends:
        ws = clients.get(fid)
        if ws is not None:
            try:
                await ws.send_json(payload)
            except Exception:
                pass


async def _broadcast_all(app, payload: dict) -> None:
    """向所有在线龙虾 WebSocket 推送 payload（全服广播）。"""
    clients: dict = getattr(app.state, "ws_clients", {})
    for ws in clients.values():
        try:
            await ws.send_json(payload)
        except Exception:
            pass


def _broadcast_all_sync(app, payload: dict) -> None:
    """同步上下文全服广播（静默忽略推送失败）。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast_all(app, payload))
    except RuntimeError:
        # no running loop — skip silently
        pass


broadcast_all_sync = _broadcast_all_sync


# ─── Background tasks ───────────────────────────────────────────────

async def _bg_persist_move(user_id: int, x: int, y: int):
    try:
        from app.models import MovementEvent
    except ImportError:
        return
    db = next(get_db())
    try:
        db.add(MovementEvent(user_id=user_id, x=x, y=y, created_at=datetime.now(timezone.utc)))
        db.commit()
    except Exception as exc:
        logger.warning("persist move failed: %s", exc)
    finally:
        db.close()


async def _bg_update_user_xy(user_id: int, x: int, y: int):
    db = next(get_db())
    try:
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            u.last_x = x
            u.last_y = y
            db.commit()
    except Exception as exc:
        logger.warning("update xy failed: %s", exc)
    finally:
        db.close()


async def _bg_delete_acked(user_id: int, acked_ids: list):
    """
    处理消息已读（ack）：
    1. 将对方的消息标记 read_at（告知发送方已读）
    2. 通知发送方（通过 WS）：message_read
    3. 删除 social_events 中对应的记录（不删除 Message 本体）
    """
    db = next(get_db())
    try:
        id_nums = [
            int(aid[4:]) for aid in acked_ids
            if isinstance(aid, str) and aid.startswith("msg_") and aid[4:].isdigit()
        ]
        if not id_nums:
            return

        now = datetime.now(timezone.utc)

        # 1. 找出这些消息的发送方（用于通知他们）
        from app.models import Message
        messages = db.query(Message).filter(
            Message.id.in_(id_nums),
            Message.to_id == user_id,
        ).all()

        # 2. 标记 read_at（未读 → 已读）
        sender_to_ids: dict[int, list[int]] = {}
        for m in messages:
            if m.read_at is None:
                m.read_at = now
                sender_to_ids.setdefault(m.from_id, []).append(m.id)

        db.commit()

        # 3. 通知每个发送方：你的消息被读了
        for sender_id, msg_ids in sender_to_ids.items():
            if sender_id is None:
                continue
            app = getattr(ws_client, "_app", None)
            if app is None:
                continue
            for msg_id in msg_ids:
                push_to_ws_client_sync(
                    app, sender_id, {
                        "type": "message_read",
                        "from_id": user_id,
                        "msg_id": msg_id,
                        "read_at": now.isoformat(),
                    }
                )

        # 4. 删除 social_events 中对应的记录
        try:
            from app.models import SocialEvent
            db.query(SocialEvent).filter(
                SocialEvent.user_id == user_id,
                SocialEvent.id.in_(id_nums),
            ).delete(synchronize_session=False)
            db.commit()
        except ImportError:
            pass
    except Exception as exc:
        logger.warning("delete acked failed: %s", exc)
        db.rollback()
    finally:
        db.close()
