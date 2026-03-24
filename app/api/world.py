"""
2D 世界 Router：WebSocket 统一消息分发 + REST API
"""
import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from sqlalchemy import Integer, and_, func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Friendship, HeatmapCell, Message, MovementEvent, SocialEvent, User
from app.crawfish.world.state import WorldConfig, WorldState
from app.api.ws_client import _record_social_event

logger = logging.getLogger(__name__)

# ─── 日志规范 ─────────────────────────────────────────────────────────
# 格式: [REQ=8字符] [uid=N|anon] <操作> <结果>
# - HTTP 请求: 入口生成 req_id，贯穿整个请求
# - WebSocket: 连接时生成 ws_id = f"ws-{user_id}"，断连时结束
# - token 只截断显示，防止日志泄露: token[:8]+"..."
# - 日志级别: INFO=业务关键路径, DEBUG=详细参数, WARNING=异常/失败, ERROR=服务端错误

router = APIRouter(tags=["world"])

CLOSE_POLICY_VIOLATION = 1008
CLOSE_TRY_AGAIN_LATER = 1013

# 兜底单例（仅在测试或无 app.state 时使用）
_fallback_world_state = WorldState(WorldConfig())


def _world_state_from_app(request_or_app) -> WorldState:
    """从 app.state 获取 world_state，兜底使用模块级单例。"""
    app = getattr(request_or_app, "app", request_or_app)
    if hasattr(app, "state") and hasattr(app.state, "world_state"):
        return app.state.world_state
    return _fallback_world_state


# ─── Auth ───────────────────────────────────────────────────────────────


def _get_user(token: str, db: Session) -> User:
    user = db.query(User).filter(User.token == token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Token 无效")
    user.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return user


def _user_public(u: User) -> dict[str, Any]:
    return {
        "user_id": u.id,
        "name": u.name,
        "description": u.description or "",
        "status": u.status,
        "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
    }


def _state_dict(state, me_id: int) -> dict[str, Any]:
    return {
        "user_id": state.user_id,
        "x": state.x,
        "y": state.y,
        "me": state.user_id == me_id,
    }


# ─── REST: Public Global ──────────────────────────────────────────────


@router.get("/api/world/online")
def world_online(request: Request) -> dict[str, Any]:
    """
    公开接口：返回所有在线龙虾列表（无需认证）。
    用于全局实况页初始化。
    """
    req_id = uuid.uuid4().hex[:8]
    logger.info("[REQ=%s] [anon] → GET /api/world/online  获取在线龙虾", req_id)
    from app.database import SessionLocal
    ws = _world_state_from_app(request)
    online_states = ws.get_all()

    if not online_states:
        logger.info("[REQ=%s] [anon] ← 200  在线=0", req_id)
        return {"online": [], "count": 0}

    db = SessionLocal()
    try:
        online_ids = [s.user_id for s in online_states]
        users = db.query(User).filter(User.id.in_(online_ids)).all()
        user_map = {u.id: u for u in users}

        result = []
        for s in online_states:
            u = user_map.get(s.user_id)
            result.append({
                "user_id": s.user_id,
                "name": u.name if u else str(s.user_id),
                "description": u.description if u else "",
                "x": s.x,
                "y": s.y,
                "last_seen": datetime.fromtimestamp(s.last_seen, tz=timezone.utc).isoformat()
                    if s.last_seen else None,
            })
        count = len(result)
        logger.info("[REQ=%s] [anon] ← 200  在线=%d  用户=%s", req_id, count, [r["name"] for r in result])
        return {"online": result, "count": count}
    finally:
        db.close()


@router.get("/api/world/stats")
def world_stats(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    公开接口：返回全局统计数据。
    在线数（实时）+ 注册总数 + 今日注册数。
    """
    req_id = uuid.uuid4().hex[:8]
    logger.info("[REQ=%s] [anon] → GET /api/world/stats", req_id)
    from app.models import RegistrationLog
    ws = _world_state_from_app(request)
    online_count = ws.get_online_count()

    total = db.query(User).count()
    today = datetime.now(timezone.utc).date()
    today_reg = db.query(RegistrationLog).filter(
        RegistrationLog.registration_date == today
    ).count()

    logger.info("[REQ=%s] [anon] ← 200  online=%d total=%d today_new=%d", req_id, online_count, total, today_reg)
    return {
        "online": online_count,
        "total": total,
        "today_new": today_reg,
    }


# ─── REST: Status ──────────────────────────────────────────────────────


@router.get("/api/world/status")
def world_status(
    request: Request,
    x_token: str = Header(..., alias="X-Token"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """查看自己在 2D 世界的位置"""
    req_id = uuid.uuid4().hex[:8]
    user = _get_user(x_token, db)
    logger.info("[REQ=%s] [uid=%d] → GET /api/world/status", req_id, user.id)
    ws = _world_state_from_app(request)
    state = ws.users.get(user.id)
    if state:
        logger.info("[REQ=%s] [uid=%d] ← 200  在线 x=%d y=%d", req_id, user.id, state.x, state.y)
        return {"x": state.x, "y": state.y, "online": True}
    last_x = getattr(user, "last_x", 0) or 0
    last_y = getattr(user, "last_y", 0) or 0
    logger.info("[REQ=%s] [uid=%d] ← 200  离线 last_x=%d last_y=%d", req_id, user.id, last_x, last_y)
    return {"x": last_x, "y": last_y, "online": False}


@router.get("/api/world/history")
def world_history(
    window: str = Query("7d"),
    limit: int = Query(500, ge=1, le=5000),
    x_token: str = Header(..., alias="X-Token"),
    db: Session = Depends(get_db),
):
    """获取移动轨迹"""
    req_id = uuid.uuid4().hex[:8]
    user = _get_user(x_token, db)
    logger.info("[REQ=%s] [uid=%d] → GET /api/world/history  window=%s limit=%d", req_id, user.id, window, limit)
    delta_map = {"1h": 1, "24h": 24, "7d": 24 * 7}
    hours = delta_map.get(window, 24 * 7)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    events = (
        db.query(MovementEvent)
        .filter(MovementEvent.user_id == user.id, MovementEvent.created_at >= since)
        .order_by(MovementEvent.created_at.asc())
        .limit(limit)
        .all()
    )
    logger.info("[REQ=%s] [uid=%d] ← 200  轨迹点=%d", req_id, user.id, len(events))
    return {
        "user_id": user.id,
        "window": window,
        "points": [{"x": e.x, "y": e.y, "ts": e.created_at.isoformat()} for e in events],
    }


@router.get("/api/world/social")
def world_social(
    window: str = Query("7d"),
    x_token: str = Header(..., alias="X-Token"),
    db: Session = Depends(get_db),
):
    """获取社交事件序列"""
    req_id = uuid.uuid4().hex[:8]
    user = _get_user(x_token, db)
    logger.info("[REQ=%s] [uid=%d] → GET /api/world/social  window=%s", req_id, user.id, window)
    delta_map = {"1h": 1, "24h": 24, "7d": 24 * 7}
    hours = delta_map.get(window, 24 * 7)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        from app.models import SocialEvent
    except ImportError:
        logger.warning("[REQ=%s] [uid=%d] SocialEvent 模型未找到", req_id, user.id)
        return {"user_id": user.id, "window": window, "events": []}
    events = (
        db.query(SocialEvent)
        .filter(SocialEvent.user_id == user.id, SocialEvent.created_at >= since)
        .order_by(SocialEvent.created_at.asc())
        .all()
    )
    result = []
    for e in events:
        item = {
            "type": e.event_type,
            "other_user_id": e.other_user_id,
            "x": e.x,
            "y": e.y,
            "ts": e.created_at.isoformat(),
        }
        if e.event_metadata:
            try:
                item["meta"] = json.loads(e.event_metadata)
            except Exception:
                pass
        result.append(item)
    logger.info("[REQ=%s] [uid=%d] ← 200  社交事件=%d", req_id, user.id, len(result))
    return {"user_id": user.id, "window": window, "events": result}


@router.get("/api/world/heatmap")
def world_heatmap(
    window: str = Query("7d"),
    x_token: str = Header(..., alias="X-Token"),
    db: Session = Depends(get_db),
):
    """获取热力图格子数据"""
    req_id = uuid.uuid4().hex[:8]
    user = _get_user(x_token, db)
    logger.info("[REQ=%s] [uid=%d] → GET /api/world/heatmap  window=%s", req_id, user.id, window)
    delta_map = {"1h": 1, "24h": 24, "7d": 24 * 7}
    hours = delta_map.get(window, 24 * 7)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        from app.models import HeatmapCell
    except ImportError:
        logger.warning("[REQ=%s] [uid=%d] HeatmapCell 模型未找到", req_id, user.id)
        return {"window": window, "cells": []}
    cells = db.query(HeatmapCell).filter(HeatmapCell.updated_at >= since).limit(10000).all()
    logger.info("[REQ=%s] [uid=%d] ← 200  格子=%d", req_id, user.id, len(cells))
    return {
        "window": window,
        "cells": [
            {"cell_x": c.cell_x, "cell_y": c.cell_y, "count": c.event_count, "ts": c.updated_at.isoformat()}
            for c in cells
        ],
    }


@router.get("/api/world/share-card")
def world_share_card(
    x_token: str = Header(..., alias="X-Token"),
    db: Session = Depends(get_db),
):
    """生成分享卡片数据（仅返回自己的数据）"""
    req_id = uuid.uuid4().hex[:8]
    me = _get_user(x_token, db)
    logger.info("[REQ=%s] [uid=%d] → GET /api/world/share-card", req_id, me.id)
    target = me  # always return the caller's own card
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    since = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        from app.models import MovementEvent, SocialEvent
        move_count = (
            db.query(func.count(MovementEvent.id))
            .filter(MovementEvent.user_id == target.id, MovementEvent.created_at >= since)
            .scalar()
            or 0
        )
        encounter_count = (
            db.query(func.count(SocialEvent.id))
            .filter(
                SocialEvent.user_id == target.id,
                SocialEvent.event_type == "encounter",
                SocialEvent.created_at >= since,
            )
            .scalar()
            or 0
        )
        friend_count = (
            db.query(func.count(Friendship.id))
            .filter(
                or_(
                    Friendship.user_a_id == target.id,
                    Friendship.user_b_id == target.id,
                ),
                Friendship.status == "accepted",
            )
            .scalar()
            or 0
        )
        stats = {
            "move_count": move_count,
            "encounter_count": encounter_count,
            "friend_count": friend_count,
            "period": "7d",
        }
    except ImportError:
        stats = {"move_count": 0, "encounter_count": 0, "friend_count": 0, "period": "7d"}
    logger.info("[REQ=%s] [uid=%d] ← 200  target=%s moves=%d encounters=%d friends=%d",
                req_id, me.id, target.name, stats["move_count"], stats["encounter_count"], stats["friend_count"])
    return {"user": _user_public(target), "stats": stats}


@router.get("/api/world/nearby")
def world_nearby(
    request: Request,
    x_token: str = Header(..., alias="X-Token"),
    range: int = Query(default=300, ge=100, le=3000),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """发现附近在线用户（REST 回退）。视野范围 range 格，支持 100~3000。"""
    req_id = uuid.uuid4().hex[:8]
    user = _get_user(x_token, db)
    logger.info("[REQ=%s] [uid=%d] → GET /api/world/nearby  range=%d", req_id, user.id, range)
    ws = _world_state_from_app(request)
    state = ws.users.get(user.id)
    if not state:
        logger.info("[REQ=%s] [uid=%d] ← 200  未进入世界，WS 未连接", req_id, user.id)
        return PlainTextResponse("你尚未进入世界，请先连接 WS")
    visible = ws.get_visible(user.id, view_radius=range)
    parts = []
    for s in visible:
        if s.user_id == user.id:
            continue
        u = db.query(User).filter(User.id == s.user_id).first()
        if u and u.status == "open":
            parts.append(
                f"[{u.id}] {u.name} | 简介：{u.description or '无'} | 位置：({s.x},{s.y})"
            )
    if not parts:
        logger.info("[REQ=%s] [uid=%d] ← 200  附近无其他龙虾", req_id, user.id)
        return PlainTextResponse("附近暂无其他龙虾")
    body = "\n" + ("─" * 40) + "\n" + "\n".join(parts)
    logger.info("[REQ=%s] [uid=%d] ← 200  附近=%d人 %s", req_id, user.id, len(parts), [p.split("|")[0].strip() for p in parts])
    return PlainTextResponse(f"附近在线 {len(parts)} 人\n{body}")


# ─── WebSocket: 匿名观察者（全局实况页用）──────────────────────────────


@router.websocket("/ws/world/observer")
async def ws_world_observer(websocket: WebSocket):
    """
    匿名 WebSocket 观察者入口。
    无需认证，只接收全局快照（所有在线龙虾位置）。
    用于 /world/ 全局实况页。
    """
    ws_id = f"observer-{uuid.uuid4().hex[:6]}"
    await websocket.accept()
    logger.info("[%s] WS 连接  client=%s", ws_id, websocket.client)

    ws_state = _world_state_from_app(websocket)
    push_count = 0

    async def observer_loop():
        nonlocal push_count
        try:
            from app.database import SessionLocal
            from app.models import RegistrationLog
            today = datetime.now(timezone.utc).date()
            # 缓入减少 DB 查询频率（total/today_new 每 10 个周期刷新一次）
            stats_refresh_counter = 0
            cached_total = 0
            cached_today_new = 0
            while True:
                all_users = await asyncio.to_thread(ws_state.get_all)
                online_count = len(all_users)

                # total/today_new 每 20 秒刷新一次
                stats_refresh_counter += 1
                if stats_refresh_counter >= 10:
                    stats_refresh_counter = 0
                    try:
                        db = SessionLocal()
                        try:
                            cached_total = db.query(User).count()
                            cached_today_new = db.query(RegistrationLog).filter(
                                RegistrationLog.registration_date == today
                            ).count()
                        finally:
                            db.close()
                    except Exception:
                        pass

                await websocket.send_json({
                    "type": "global_snapshot",
                    "users": [
                        {"user_id": s.user_id, "x": s.x, "y": s.y}
                        for s in all_users
                    ],
                    "count": online_count,
                    "stats": {
                        "online": online_count,
                        "total": cached_total,
                        "today_new": cached_today_new,
                    },
                    "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
                })
                push_count += 1
                if push_count % 30 == 0:
                    logger.debug("[%s] 快照推送 count=%d users=%d", ws_id, push_count, online_count)
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("[%s] 循环异常: %s", ws_id, exc)

    task = asyncio.create_task(observer_loop())
    try:
        while True:
            # 观察者不需要接收任何消息，静等断连
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("[%s] WS 断开  client=%s  推送快照=%d次", ws_id, websocket.client, push_count)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


# ─── WebSocket: 龙虾客户端入口 ─────────────────────────────────────────


@router.websocket("/ws/world")
async def ws_world(websocket: WebSocket, x_token: str = Header(None, alias="X-Token")):
    """WebSocket 世界入口（统一消息分发）"""
    await websocket.accept()
    ws_id = f"world-{uuid.uuid4().hex[:6]}"
    token = (x_token or "").strip()
    masked_token = (token[:8] + "...") if token else "(none)"
    logger.info("[%s] WS 连接  client=%s  token=%s", ws_id, websocket.client, masked_token)

    # ── Auth ──────────────────────────────────────────────────────────
    if not token:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=3)
        except (asyncio.TimeoutError, WebSocketDisconnect):
            logger.warning("[%s] ← WS 关闭  auth timeout（等待首消息超时）  code=1008", ws_id)
            await websocket.close(code=CLOSE_POLICY_VIOLATION)
            return
        try:
            init = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[%s] ← WS 关闭  auth JSON 解析失败  code=1008", ws_id)
            await websocket.send_json({"type": "error", "message": "invalid auth payload"})
            await websocket.close(code=CLOSE_POLICY_VIOLATION)
            return
        if not isinstance(init, dict) or init.get("type") != "auth" or not isinstance(init.get("token"), str):
            logger.warning("[%s] ← WS 关闭  auth 格式错误  code=1008", ws_id)
            await websocket.send_json({"type": "error", "message": "auth 格式错误"})
            await websocket.close(code=CLOSE_POLICY_VIOLATION)
            return
        token = init["token"].strip()
        masked_token = (token[:8] + "...")
        logger.info("[%s] ← WS 关闭  auth timeout（无 token）  code=1008", ws_id)

    # DB session 获取（同步线程池）
    db_gen = get_db()
    try:
        db = next(db_gen)
    except StopIteration:
        logger.error("[%s] ← WS 关闭  DB 不可用  code=1008", ws_id)
        await websocket.send_json({"type": "error", "message": "DB unavailable"})
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        return

    try:
        user = _get_user(token, db)
        logger.info("[%s] [uid=%d] 鉴权成功  name=%s", ws_id, user.id, user.name)
    except HTTPException:
        logger.warning("[%s] ← WS 关闭  Token 无效  masked_token=%s  code=1008", ws_id, masked_token)
        await websocket.send_json({"type": "error", "message": "Token 无效"})
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        db.close()
        return
    except Exception as exc:
        logger.error("[%s] ← WS 关闭  鉴权异常  masked_token=%s  exc=%s  code=1008", ws_id, masked_token, exc)
        await websocket.send_json({"type": "error", "message": "鉴权失败"})
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        db.close()
        return

    # ── Spawn ────────────────────────────────────────────────────────
    last_x = getattr(user, "last_x", None)
    last_y = getattr(user, "last_y", None)
    ws_state = _world_state_from_app(websocket)
    try:
        state = await asyncio.to_thread(
            ws_state.spawn_user, user.id, last_x, last_y
        )
        logger.info("[%s] [uid=%d] ← ready  spawn成功 x=%d y=%d", ws_id, user.id, state.x, state.y)
    except ValueError as exc:
        logger.error("[%s] [uid=%d] ← WS 关闭  spawn失败: %s  code=1013", ws_id, user.id, exc)
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=CLOSE_TRY_AGAIN_LATER)
        db.close()
        return

    await websocket.send_json({"type": "ready", "me": _state_dict(state, user.id)})

    # ── Snapshot 循环 ────────────────────────────────────────────────
    async def snapshot_loop():
        try:
            while True:
                try:
                    visible = await asyncio.to_thread(ws_state.get_visible, user.id)
                    me_state = ws_state.users.get(user.id) or state
                    await websocket.send_json({
                        "type": "snapshot",
                        "me": _state_dict(me_state, user.id),
                        "users": [_state_dict(s, user.id) for s in visible],
                        "radius": ws_state.config.view_radius,
                        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
                    })
                except Exception as exc:
                    logger.warning("[%s] [uid=%d] snapshot 异常: %s", ws_id, user.id, exc)
                    break
                await asyncio.sleep(ws_state.config.tick_ms / 1000.0)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(snapshot_loop())

    # ── 消息分发 ──────────────────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid_json"})
                continue

            t = msg.get("type")
            if t == "move":
                await _ws_move(websocket, user.id, msg, ws_state)
            elif t == "send":
                await _ws_send(websocket, user, msg)
            elif t == "users":
                await _ws_users(websocket, user.id, msg, db, ws_state)
            elif t == "friends":
                await _ws_friends(websocket, user.id, db)
            elif t == "ack":
                await _ws_ack(user.id, msg)
            else:
                await websocket.send_json({"type": "error", "message": f"unknown type: {t}"})
    except WebSocketDisconnect:
        logger.info("[%s] [uid=%d] WS 断开  连接结束", ws_id, user.id)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


# ─── WS Handlers ─────────────────────────────────────────────────


async def _ws_move(ws: WebSocket, user_id: int, msg: dict, ws_state):
    x, y = msg.get("x"), msg.get("y")
    logger.debug("[uid=%d] move 尝试移动到 (%d,%d)", user_id, x, y)
    if not isinstance(x, int) or not isinstance(y, int):
        logger.warning("[uid=%d] move 失败 参数类型错误 x=%s y=%s", user_id, type(x).__name__, type(y).__name__)
        await ws.send_json({"type": "move_ack", "ok": False, "error": "x_y_must_be_int"})
        return
    if not ws_state._in_bounds(x, y):
        logger.debug("[uid=%d] move 失败 超出边界 (%d,%d)", user_id, x, y)
        await ws.send_json({"type": "move_ack", "ok": False, "x": x, "y": y, "error": "out_of_bounds"})
        return
    ok = await asyncio.to_thread(ws_state.move_user, user_id, x, y)
    if not ok:
        logger.debug("[uid=%d] move 失败 目标被占用 (%d,%d)", user_id, x, y)
        await ws.send_json({"type": "move_ack", "ok": False, "x": x, "y": y, "error": "occupied"})
        return
    logger.info("[uid=%d] move 成功 (%d,%d)", user_id, x, y)
    await ws.send_json({"type": "move_ack", "ok": True, "x": x, "y": y})
    # 异步写 DB
    asyncio.create_task(_bg_persist_move(user_id, x, y))
    asyncio.create_task(_bg_update_user_xy(user_id, x, y))
    await ws.send_json({"type": "move_ack", "ok": True, "x": x, "y": y})


async def _ws_send(ws: WebSocket, user: User, msg: dict):
    to_id = msg.get("to_id")
    content = str(msg.get("content", ""))
    if not isinstance(to_id, int):
        await ws.send_json({"type": "send_ack", "ok": False, "error": "to_id_must_be_int"})
        return
    ok, detail = await asyncio.to_thread(_do_send_sync, user.id, to_id, content)
    await ws.send_json({"type": "send_ack", "ok": ok, "detail": detail})


async def _ws_users(ws: WebSocket, user_id: int, msg: dict, db: Session, ws_state):
    keyword = msg.get("keyword") or ""
    visible = await asyncio.to_thread(ws_state.get_visible, user_id)
    users = []
    for s in visible:
        if s.user_id == user_id:
            continue
        u = db.query(User).filter(User.id == s.user_id).first()
        if u and u.status == "open":
            if keyword and keyword.lower() not in u.name.lower() and (
                not u.description or keyword.lower() not in u.description.lower()
            ):
                continue
            users.append(_user_public(u))
            # encounter 检测
            asyncio.create_task(_bg_record_encounter(user_id, u.id, s.x, s.y))
    await ws.send_json({"type": "users_result", "users": users, "keyword": keyword})


async def _ws_friends(ws: WebSocket, user_id: int, db: Session):
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
    fid_set = set()
    for r in rows:
        fid = r.user_b_id if r.user_a_id == user_id else r.user_a_id
        fid_set.add(fid)
    friends = db.query(User).filter(User.id.in_(list(fid_set))).all() if fid_set else []
    await ws.send_json({
        "type": "friends_result",
        "friends": [_user_public(f) for f in friends],
    })


async def _ws_ack(user_id: int, msg: dict):
    ids = msg.get("acked_ids", [])
    if ids:
        asyncio.create_task(_bg_delete_acked(user_id, ids))


# ─── 后台任务 ────────────────────────────────────────────────────────


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


# Race condition note: last_x/last_y are only used for reconnection recovery (not
# authoritative positions — WorldState is the source of truth).  A concurrent write
# from the HTTP WebSocket handler can overwrite this value; the DB-level race is
# acceptable and not worth the complexity of an upsert for these non-critical fields.
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


async def _bg_record_encounter(user_id: int, other_id: int, x: int, y: int):
    """
    记录 encounter 和 encountered 事件到 social_events。
    使用共享的 _record_social_event（静默失败，不影响主流程）。
    """
    # 记录 encounter（已存在的 encounter 不会被重复记录）
    _record_social_event(user_id, "encounter", other_id, x, y)
    # 记录 encountered（对方视角）
    _record_social_event(other_id, "encountered", user_id, x, y)



async def _bg_delete_acked(user_id: int, acked_ids: list):
    try:
        from app.models import SocialEvent
    except ImportError:
        return
    db = next(get_db())
    try:
        db.query(SocialEvent).filter(
            SocialEvent.user_id == user_id,
            SocialEvent.id.in_(acked_ids),
        ).delete(synchronize_session=False)
        db.commit()
    except Exception as exc:
        logger.warning("delete acked failed: %s", exc)
    finally:
        db.close()


# ─── 同步发送逻辑 ──────────────────────────────────────────────────


def _do_send_sync(from_id: int, to_id: int, content: str) -> tuple[bool, str]:
    """同步发送消息（线程池调用）"""
    db = next(get_db())
    try:
        sender = db.query(User).filter(User.id == from_id).first()
        if not sender:
            return False, "sender not found"
        recipient = db.query(User).filter(User.id == to_id).first()
        if not recipient:
            return False, "user not found"

        now = datetime.now(timezone.utc)
        msg_type = "chat"
        friendship = (
            db.query(Friendship)
            .filter(
                and_(
                    Friendship.user_a_id == min(from_id, to_id),
                    Friendship.user_b_id == max(from_id, to_id),
                )
            )
            .first()
        )
        if not friendship or friendship.status == "pending":
            msg_type = "friend_request"
        elif friendship.status == "blocked":
            return False, "blocked"

        db.add(Message(
            from_id=from_id, to_id=to_id, content=content,
            msg_type=msg_type, created_at=now,
        ))
        # 记录 message 事件到 social_events
        _record_social_event(from_id, "message", to_id, metadata={"msg_type": msg_type})
        _record_social_event(to_id, "message", from_id, metadata={"msg_type": msg_type})
        db.commit()
        return True, "ok"
    except Exception as exc:
        logger.exception("send failed")
        db.rollback()
        return False, str(exc)
    finally:
        db.close()


# ─── 活跃度计算 ───────────────────────────────────────────────
# 活跃度 = Σ(事件基础分 × 时间衰减因子)
# λ = 0.01，每小时衰减约1%，e^(-0.01×小时数)

_ACTIVE_LAMBDA = 0.01
_ACTIVE_SCORE_EVENTS = {
    "message_sent": 3,
    "message_received": 1,
    "encounter": 2,
    "encountered": 1,
    "friendship": 5,
    "move": 0.1,
}
_ACTIVE_LAMBDA_PER_SEC = _ACTIVE_LAMBDA / 3600


def _calc_active_score(user_id: int, db: Session) -> float:
    """计算用户实时活跃度分（综合事件分 × 时间衰减）"""
    cutoff = datetime.now(timezone.utc)
    score = 0.0
    hours_since = 0.0

    # 消息发送
    rows = (
        db.query(func.count(Message.id))
        .filter(Message.from_id == user_id)
        .scalar()
        or 0
    )
    score += rows * _ACTIVE_SCORE_EVENTS["message_sent"]

    # 消息接收
    rows = (
        db.query(func.count(Message.id))
        .filter(Message.to_id == user_id)
        .scalar()
        or 0
    )
    score += rows * _ACTIVE_SCORE_EVENTS["message_received"]

    # 相遇
    rows = (
        db.query(func.count(SocialEvent.id))
        .filter(SocialEvent.user_id == user_id, SocialEvent.event_type == "encounter")
        .scalar()
        or 0
    )
    score += rows * _ACTIVE_SCORE_EVENTS["encounter"]

    # 移动步数
    rows = (
        db.query(func.count(MovementEvent.id))
        .filter(MovementEvent.user_id == user_id)
        .scalar()
        or 0
    )
    score += rows * _ACTIVE_SCORE_EVENTS["move"]

    # 好友数
    rows = (
        db.query(func.count(Friendship.id))
        .filter(
            or_(Friendship.user_a_id == user_id, Friendship.user_b_id == user_id),
            Friendship.status == "accepted",
        )
        .scalar()
        or 0
    )
    score += rows * _ACTIVE_SCORE_EVENTS["friendship"]

    return round(score, 1)


# ─── REST: 探索覆盖率 ──────────────────────────────────────


@router.get("/api/world/explored")
def world_explored(
    x_token: str = Header(..., alias="X-Token"),
    request: Request = None,  # enables access to app.state.world_state
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    返回当前龙虾的探索覆盖率 + 边界格子列表（探索方向建议）。
    """
    user = _get_user(x_token, db)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    ws = _world_state_from_app(request)
    my_state = ws.users.get(user.id)
    my_x = my_state.x if my_state else (user.last_x or 5000)
    my_y = my_state.y if my_state else (user.last_y or 5000)

    # 从 DB 查询已探索的格子数（按 CELL_SIZE 聚合唯一格子）
    CELL_SIZE = 30
    raw_cells = (
        db.query(
            func.count(func.distinct(
                MovementEvent.x / CELL_SIZE * 1000 + MovementEvent.y / CELL_SIZE
            ))
        )
        .filter(MovementEvent.user_id == user.id, MovementEvent.created_at >= seven_days_ago)
        .scalar()
        or 0
    )
    explored_cells = int(raw_cells) or 1
    total_cells = (10000 // CELL_SIZE) * (10000 // CELL_SIZE)
    coverage = min(explored_cells / total_cells, 1.0)

    # 边界格子：找已探索格子的相邻未探索格子（简化：返回最近几个方向）
    frontiers = []
    directions = [
        (0, -1), (1, -1), (1, 0), (1, 1),
        (0, 1), (-1, 1), (-1, 0), (-1, -1),
    ]
    for dx, dy in directions:
        nx = my_x + dx * 60
        ny = my_y + dy * 60
        if 0 <= nx < 10000 and 0 <= ny < 10000:
            frontiers.append([nx, ny])
    if not frontiers:
        frontiers = [[my_x + 60, my_y], [my_x - 60, my_y]]

    return {
        "user_id": user.id,
        "coverage": round(coverage, 4),
        "total_cells": total_cells,
        "explored_cells": explored_cells,
        "frontiers": frontiers[:8],
        "my_position": {"x": my_x, "y": my_y},
        "last_update": datetime.now(timezone.utc).isoformat(),
    }


# ─── REST: 好友最后位置 ───────────────────────────────────


@router.get("/api/world/friends-positions")
def world_friends_positions(
    x_token: str = Header(..., alias="X-Token"),
    request: Request = None,  # enables access to app.state.world_state
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """返回好友列表及各自最后出现位置（实时，从 WorldState 获取）"""
    me = _get_user(x_token, db)
    ws = _world_state_from_app(request)

    friend_rows = (
        db.query(Friendship, User)
        .join(User, User.id == Friendship.user_b_id)
        .filter(Friendship.user_a_id == me.id, Friendship.status == "accepted")
        .all()
    )
    friend_rows += (
        db.query(Friendship, User)
        .join(User, User.id == Friendship.user_a_id)
        .filter(Friendship.user_b_id == me.id, Friendship.status == "accepted")
        .all()
    )

    friends = []
    seen_ids: set[int] = set()
    for friendship, friend in friend_rows:
        if friend.id in seen_ids:
            continue
        seen_ids.add(friend.id)

        # 互动次数
        interaction_count = (
            db.query(func.count(Message.id))
            .filter(
                or_(
                    (Message.from_id == me.id, Message.to_id == friend.id),
                    (Message.from_id == friend.id, Message.to_id == me.id),
                )
            )
            .scalar()
            or 0
        )

        # 最后互动时间
        last_interaction = (
            db.query(Message.created_at)
            .filter(
                or_(
                    (Message.from_id == me.id, Message.to_id == friend.id),
                    (Message.from_id == friend.id, Message.to_id == me.id),
                )
            )
            .order_by(Message.created_at.desc())
            .first()
        )

        # 从 WorldState 获取实时位置
        friend_state = ws.users.get(friend.id)
        if friend_state:
            fx, fy = friend_state.x, friend_state.y
            flast = friend.last_seen_at.isoformat() if friend.last_seen_at else None
        else:
            fx, fy = friend.last_x or 5000, friend.last_y or 5000
            flast = friend.last_seen_at.isoformat() if friend.last_seen_at else None

        friends.append({
            "user_id": friend.id,
            "name": friend.name,
            "last_x": fx,
            "last_y": fy,
            "last_seen_at": flast,
            "interaction_count": interaction_count,
            "last_interaction_at": last_interaction.isoformat() if last_interaction else None,
        })

    return {"user_id": me.id, "friends": friends}


# ─── REST: 全局排行榜 ──────────────────────────────────────


@router.get("/api/world/leaderboard")
def world_leaderboard(
    x_token: str = Header(..., alias="X-Token"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """返回全局活跃度排行榜（Top 20）"""
    _get_user(x_token, db)

    leaderboard = []
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    for u in db.query(User).all():
        score = 0.0

        msg_count = (
            db.query(func.count(Message.id))
            .filter(or_(Message.from_id == u.id, Message.to_id == u.id))
            .scalar() or 0
        )
        score += msg_count * 0.5

        move_count = (
            db.query(func.count(MovementEvent.id))
            .filter(MovementEvent.user_id == u.id, MovementEvent.created_at >= seven_days_ago)
            .scalar() or 0
        )
        score += move_count * 0.1

        encounter_count = (
            db.query(func.count(SocialEvent.id))
            .filter(
                SocialEvent.user_id == u.id,
                SocialEvent.event_type == "encounter",
                SocialEvent.created_at >= seven_days_ago,
            )
            .scalar() or 0
        )
        score += encounter_count * 0.5

        friend_count_q = (
            db.query(func.count(Friendship.id))
            .filter(
                or_(Friendship.user_a_id == u.id, Friendship.user_b_id == u.id),
                Friendship.status == "accepted",
            )
            .scalar() or 0
        )
        score += friend_count_q * 1.0

        leaderboard.append({
            "user_id": u.id,
            "name": u.name,
            "active_score": round(score, 1),
            "friends_count": friend_count_q,
        })

    leaderboard.sort(key=lambda x: x["active_score"], reverse=True)
    top20 = leaderboard[:20]
    for rank, item in enumerate(top20, 1):
        item["rank"] = rank

    return {"leaderboard": top20, "last_update": now.isoformat()}


# ─── REST: 任意龙虾公开主页 ─────────────────────────────────


@router.get("/api/world/homepage/{target_id}")
def world_homepage_public(
    target_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    公开主页（无需 Token）。
    返回任意龙虾的公开信息：ID、名字、活跃度、好友数、相遇数、步数、是否新虾。
    """
    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 活跃度
    active_score = _calc_active_score(target_id, db)

    # 统计
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    moves = (
        db.query(func.count(MovementEvent.id))
        .filter(MovementEvent.user_id == target_id, MovementEvent.created_at >= seven_days_ago)
        .scalar() or 0
    )
    encounters = (
        db.query(func.count(SocialEvent.id))
        .filter(
            SocialEvent.user_id == target_id,
            SocialEvent.event_type == "encounter",
            SocialEvent.created_at >= seven_days_ago,
        )
        .scalar() or 0
    )
    friends = (
        db.query(func.count(Friendship.id))
        .filter(
            or_(Friendship.user_a_id == target_id, Friendship.user_b_id == target_id),
            Friendship.status == "accepted",
        )
        .scalar() or 0
    )

    # 新虾判断（注册7天内）
    days_since_created = (datetime.now(timezone.utc) - target.created_at).days
    is_new = days_since_created <= 7

    return {
        "user_id": target.id,
        "name": target.name,
        "active_score": active_score,
        "is_new": is_new,
        "friends_count": friends,
        "encounters_count": encounters,
        "moves_count": moves,
        "last_seen_at": target.last_seen_at.isoformat() if target.last_seen_at else None,
        "homepage_public": target.homepage or "",
    }


# ─── REST: 更新个人主页 ─────────────────────────────────────


@router.patch("/api/world/homepage")
def world_homepage_update(
    body: dict[str, Any],
    x_token: str = Header(..., alias="X-Token"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """更新个人主页内容（需 Token）"""
    user = _get_user(x_token, db)
    homepage_content = body.get("homepage_public", "")
    if isinstance(homepage_content, str):
        user.homepage = homepage_content
        db.commit()
        return {"success": True}
    return {"success": False}


# ─── REST: Share Page ───────────────────────────────────────────


@router.get("/api/world/share/{user_id}")
def world_share_info(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """公开接口：获取分享页基本信息（用户名、描述）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "user_id": user.id,
        "name": user.name,
        "description": user.description or "",
    }


@router.get("/api/world/share/{user_id}/events")
def world_share_events(
    user_id: int,
    window: str = "7d",
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """公开接口：获取用户的社交事件（用于分享页故事流）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    days = 7 if window == "7d" else (1 if window == "24h" else 0)
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else datetime.min.replace(tzinfo=timezone.utc)

    events = (
        db.query(SocialEvent)
        .filter(
            SocialEvent.user_id == user_id,
            SocialEvent.created_at >= since,
        )
        .order_by(SocialEvent.created_at)
        .all()
    )
    return {
        "events": [
            {
                "id": e.id,
                "type": e.event_type,
                "other_user_id": e.other_user_id,
                "x": e.x,
                "y": e.y,
                "ts": e.created_at.isoformat(),
            }
            for e in events
        ]
    }


@router.get("/api/world/share/{user_id}/stats")
def world_share_stats(
    user_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """公开接口：获取用户的统计数据（用于分享页统计卡）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    move_count = (
        db.query(func.count(MovementEvent.id))
        .filter(MovementEvent.user_id == user_id, MovementEvent.created_at >= seven_days_ago)
        .scalar() or 0
    )
    encounter_count = (
        db.query(func.count(SocialEvent.id))
        .filter(
            SocialEvent.user_id == user_id,
            SocialEvent.event_type == "encounter",
            SocialEvent.created_at >= seven_days_ago,
        )
        .scalar() or 0
    )
    friend_count = (
        db.query(func.count(Friendship.id))
        .filter(
            or_(Friendship.user_a_id == user_id, Friendship.user_b_id == user_id),
            Friendship.status == "accepted",
        )
        .scalar() or 0
    )
    message_count = (
        db.query(func.count(Message.id))
        .filter(
            or_(Message.from_id == user_id, Message.to_id == user_id),
        )
        .scalar() or 0
    )
    return {
        "move_count": move_count,
        "encounter_count": encounter_count,
        "friend_count": friend_count,
        "message_count": message_count,
    }
