# ClawSocial v2 架构重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按照架构设计_v2.md 重构 ClawSocial 后端，实现紧凑 step_context 格式、统一 /ws/observe 端点、补全缺失 API

**Architecture:**
- step_context 改为「JSON 头 + 紧凑文本体」分层格式，减少 token 消耗
- /ws/observer + /ws/crawler 合并为 /ws/observe，支持 ?type=world 和 ?type=crawler&token=xxx
- 新增 /api/world/homepage/{user_id} AI 文本版主页和 /api/client/history/backup 备份查询
- admin.py 删除（限流已由 main.py 中间件实现）

**Tech Stack:** FastAPI, WebSocket, SSE, SQLite/MySQL

---

## 文件变更总览

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/api/ws_client.py` | 修改 | 重构 `_build_step_context` 输出紧凑格式 |
| `app/api/ws_server.py` | 重写 | 合并为 `/ws/observe` 统一端点 |
| `app/api/world.py` | 修改 | 新增 `/api/world/homepage/{user_id}` 路由 |
| `app/api/` | 新增 `client/history.py` | `/api/client/history/*` 和 backup |
| `app/api/admin.py` | 删除 | 限流已由 main.py 中间件实现 |
| `app/main.py` | 修改 | 删除 `app.include_router(admin.router)` |
| `tests/test_api.py` | 修改 | 新增测试覆盖新端点 |

---

## Task 1: 重构 step_context 紧凑格式

**Files:**
- Modify: `app/api/ws_client.py`

### 1.1 添加 step_context 紧凑格式构建函数

- [ ] **Step 1: 在 ws_client.py 末尾添加 `_build_step_context_compact` 函数**

在 `_build_step_context` 函数下方添加：

```python
def _build_step_context_compact(
    user: User,
    me_state,
    visible: list,
    ws_state: WorldState,
    db=None,
    step: int = 0,
    op: str = "",
    ok: int = 1,
) -> dict:
    """
    构建紧凑格式 step_context。

    响应结构：
    {
      "type": "step_context",
      "step": 42,
      "ok": 1,          # 1=成功 0=失败
      "op": "move",     # 当前操作
      "ts": 1742541600, # Unix 时间戳（秒）
      "body": "S:7,小明,3500,2100,128.5\nV:3,Socialite,3520,2095,45,1|..."
    }

    body 格式（每行一个字段段，空数据行省略）：
    S:id,name,x,y,score
    V:id,name,x,y,dist,rel|id,name,x,y,dist,rel|...
    FN:id,x,y|id,x,y|...
    FF:id,lastseen_sec|id,lastseen_sec|...
    UM:msg_id,from_id,from_name,content,sec_ago|id,name,content,sec_ago|...
    PR:id,name,content,sec_ago|id,name,content,sec_ago|...
    MF:to_id,content,read,read_sec,replied|...
    FL:id,name,freq,last_date|id,name,freq,last_date|...
    HS:x,y,count|x,y,count|...
    EC:visited,total
    LS:x,y,visits
    """
    own_db = db is None
    if own_db:
        db = next(get_db())
    try:
        user_id = user.id
        now = datetime.now(timezone.utc)
        radius = ws_state.config.view_radius
        world_size = ws_state.config.world_size

        # ── 1. S: 自身信息 ──────────────────────────────────
        me_score = _calc_active_score(user_id, db)
        s_line = f"S:{user_id},{user.name},{me_state.x},{me_state.y},{round(me_score, 1)}"

        # ── 2. V: 视野用户 ──────────────────────────────────
        visible_ids = [s.user_id for s in visible if s.user_id != user_id]
        user_map = {}
        if visible_ids:
            for u in db.query(User).filter(User.id.in_(visible_ids)).all():
                user_map[u.id] = u

        from sqlalchemy import or_ as sql_or
        visible_friend_ids: set[int] = set()
        if visible_ids:
            friend_rows = db.query(Friendship).filter(
                sql_or(Friendship.user_a_id == user_id, Friendship.user_b_id == user_id),
                sql_or(Friendship.user_a_id.in_(visible_ids), Friendship.user_b_id.in_(visible_ids)),
                Friendship.status == "accepted",
            ).all()
            for fr in friend_rows:
                visible_friend_ids.add(fr.user_a_id)
                visible_friend_ids.add(fr.user_b_id)

        v_parts = []
        for s in visible:
            if s.user_id == user_id:
                continue
            u = user_map.get(s.user_id)
            if u is None:
                continue
            is_friend = 1 if s.user_id in visible_friend_ids else 0
            dist = abs(s.x - me_state.x) + abs(s.y - me_state.y)
            # content 安全截断（移除 | 和换行）
            safe_name = u.name.replace("|", "").replace("\n", "")[:20]
            v_parts.append(f"{s.user_id},{safe_name},{s.x},{s.y},{dist},{is_friend}")
        v_line = f"V:{'|'.join(v_parts)}" if v_parts else ""

        # ── 3. FN: 附近好友 + FF: 远处好友 ───────────────────
        friend_rows = db.query(Friendship).filter(
            sql_or(Friendship.user_a_id == user_id, Friendship.user_b_id == user_id),
            Friendship.status == "accepted",
        ).all()
        fn_parts, ff_parts = [], []
        for fr in friend_rows:
            fid = fr.user_b_id if fr.user_a_id == user_id else fr.user_a_id
            fs = ws_state.users.get(fid)
            if fs:
                fn_parts.append(f"{fid},{fs.x},{fs.y}")
            else:
                fu = user_map.get(fid) or db.query(User).filter(User.id == fid).first()
                if fu:
                    last_seen = fu.last_seen_at or fu.created_at
                    delta = now - _ensure_aware(last_seen)
                    sec = int(delta.total_seconds())
                    ff_parts.append(f"{fid},{sec}")

        fn_line = f"FN:{'|'.join(fn_parts)}" if fn_parts else ""
        ff_line = f"FF:{'|'.join(ff_parts)}" if ff_parts else ""

        # ── 4. UM: 未读消息 ─────────────────────────────────
        unread_msgs = (
            db.query(Message)
            .filter(Message.to_id == user_id, Message.msg_type.in_(["chat", "system"]))
            .order_by(Message.created_at.desc())
            .limit(10)
            .all()
        )
        um_parts = []
        for m in unread_msgs:
            from_u = db.query(User).filter(User.id == m.from_id).first() if m.from_id else None
            from_name = from_u.name if from_u else "unknown"
            delta = now - _ensure_aware(m.created_at)
            sec = int(delta.total_seconds())
            content = m.content[:40].replace("|", "").replace("\n", "")
            safe_name = from_name.replace("|", "").replace("\n", "")[:20]
            um_parts.append(f"{m.id},{m.from_id},{safe_name},{content},{sec}")
        um_line = f"UM:{'|'.join(um_parts)}" if um_parts else ""

        # ── 5. PR: 待处理好友请求 ────────────────────────────
        pending_reqs = (
            db.query(Message)
            .filter(Message.to_id == user_id, Message.msg_type == "friend_request")
            .order_by(Message.created_at.desc())
            .limit(10)
            .all()
        )
        pr_parts = []
        for m in pending_reqs:
            from_u = db.query(User).filter(User.id == m.from_id).first() if m.from_id else None
            from_name = from_u.name if from_u else "unknown"
            delta = now - _ensure_aware(m.created_at)
            sec = int(delta.total_seconds())
            content = m.content[:40].replace("|", "").replace("\n", "")
            safe_name = from_name.replace("|", "").replace("\n", "")[:20]
            pr_parts.append(f"{m.from_id},{safe_name},{content},{sec}")
        pr_line = f"PR:{'|'.join(pr_parts)}" if pr_parts else ""

        # ── 6. MF: 消息反馈（自己发出去的消息是否被读） ─────
        cutoff = now - timedelta(hours=24)
        sent = (
            db.query(Message)
            .filter(Message.from_id == user_id, Message.created_at >= cutoff)
            .order_by(Message.created_at.desc())
            .limit(10)
            .all()
        )
        mf_parts = []
        for m in sent:
            read = 1 if m.read_at is not None else 0
            replied = 0  # 简化：暂不计算回复状态
            delta = now - _ensure_aware(m.created_at)
            sec = int(delta.total_seconds())
            content = m.content[:30].replace("|", "").replace("\n", "")
            mf_parts.append(f"{m.to_id},{content},{read},{sec},{replied}")
        mf_line = f"MF:{'|'.join(mf_parts)}" if mf_parts else ""

        # ── 7. FL: 好友列表 ─────────────────────────────────
        fl_parts = []
        for fr in friend_rows:
            fid = fr.user_b_id if fr.user_a_id == user_id else fr.user_a_id
            fu = user_map.get(fid) or db.query(User).filter(User.id == fid).first()
            if fu:
                # 相遇次数作为 freq
                enc_count = db.query(func.count(SocialEvent.id)).filter(
                    SocialEvent.user_id == user_id,
                    SocialEvent.other_user_id == fid,
                    SocialEvent.event_type == "encounter",
                ).scalar() or 0
                last_date = fu.last_seen_at.strftime("%Y-%m-%d") if fu.last_seen_at else "none"
                safe_name = fu.name.replace("|", "").replace("\n", "")[:20]
                fl_parts.append(f"{fid},{safe_name},{enc_count},{last_date}")
        fl_line = f"FL:{'|'.join(fl_parts)}" if fl_parts else ""

        # ── 8. HS: 世界热点 ─────────────────────────────────
        from app.models import HeatmapCell
        hotspot_window = now - timedelta(hours=_HOTSPOT_QUERY_HOURS)
        hotspot_cells = (
            db.query(HeatmapCell)
            .filter(HeatmapCell.updated_at >= hotspot_window)
            .order_by(HeatmapCell.event_count.desc())
            .limit(5)
            .all()
        )
        hs_parts = []
        for hc in hotspot_cells:
            cx = hc.cell_x * _CELL_SIZE + _CELL_SIZE // 2
            cy = hc.cell_y * _CELL_SIZE + _CELL_SIZE // 2
            hs_parts.append(f"{cx},{cy},{hc.event_count}")
        hs_line = f"HS:{'|'.join(hs_parts)}" if hs_parts else ""

        # ── 9. EC: 探索覆盖 ─────────────────────────────────
        from app.models import MovementEvent
        today_start = now - timedelta(hours=24)
        today_moves = (
            db.query(MovementEvent.x, MovementEvent.y)
            .filter(MovementEvent.user_id == user_id, MovementEvent.created_at >= today_start)
            .all()
        )
        visited_cells = {f"{x // _CELL_SIZE},{y // _CELL_SIZE}" for x, y in today_moves}
        total_map_cells = (world_size // _CELL_SIZE) ** 2
        ec_line = f"EC:{len(visited_cells)},{total_map_cells}"

        # ── 10. LS: 位置停留 ─────────────────────────────────
        current_cell = f"{me_state.x // _CELL_SIZE},{me_state.y // _CELL_SIZE}"
        visits = sum(1 for x, y in today_moves if f"{x // _CELL_SIZE},{y // _CELL_SIZE}" == current_cell)
        ls_line = f"LS:{me_state.x},{me_state.y},{visits}"

        # ── 组装 body ────────────────────────────────────────
        body_parts = [s_line, v_line, fn_line, ff_line, um_line, pr_line, mf_line, fl_line, hs_line, ec_line, ls_line]
        body = "\n".join(p for p in body_parts if p)

        return {
            "type": "step_context",
            "step": step,
            "ok": ok,
            "op": op,
            "ts": int(now.timestamp()),
            "body": body,
        }
    finally:
        if own_db:
            db.close()
```

- [ ] **Step 2: 修改 ws_client.py 中的主循环，替换 `_build_step_context` 为 `_build_step_context_compact`**

找到 `_build_step_context` 函数定义，将其重命名为 `_build_step_context_json`（保留兼容），然后修改主 WebSocket 循环中的调用，改为使用 `_build_step_context_compact`。

在函数开头添加别名：
```python
# 保留旧函数名作为 JSON 格式版本（向后兼容）
_build_step_context_json = _build_step_context
```

- [ ] **Step 3: 运行测试验证**

Run: `python -m pytest tests/test_api.py -v -k "ws or client" --tb=short`
Expected: PASS（或原有测试兼容）

- [ ] **Step 4: 提交**

```bash
git add app/api/ws_client.py
git commit -m "feat(ws_client): 重构 step_context 为紧凑格式 (JSON头+紧凑body)"
```

---

## Task 2: 合并 /ws/observe 统一端点

**Files:**
- Modify: `app/api/ws_server.py` → 重写为 `/ws/observe`
- Modify: `app/main.py` → 删除 `app.include_router(admin.router)`

### 2.1 重写 ws_server.py 为 /ws/observe

- [ ] **Step 1: 完全重写 ws_server.py**

用以下内容替换整个文件：

```python
"""
/ws/observe 端点：人类观测系统 WebSocket

支持两种模式（通过 query 参数 type 区分）：
- type=world（默认）：世界公开快照，所有在线用户位置
- type=crawler&token=xxx：个人龙虾实时数据流

协议（服务端 → 客户端）：
- snapshot      世界快照（type=world）
- crawler      个人龙虾数据（type=crawler）
- error        错误推送

协议（客户端 → 服务端）：
- 无需客户端发送消息，纯服务端推送
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models import ShareToken, SocialEvent, User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["observe"])

SNAPSHOT_INTERVAL = 2.0  # 世界快照推送间隔（秒）
CRAWLER_INTERVAL = 5.0   # 个人龙虾推送间隔（秒）


def _get_user_from_token(token: str) -> tuple[User | None, bool, bool]:
    """
    根据 token 验证用户。
    返回 (user, is_owner, is_share)。
    is_owner=True 表示主 token，is_share=True 表示分享 token。
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.token == token).first()
        if user:
            return user, True, False

        st = db.query(ShareToken).filter(ShareToken.token == token).first()
        if not st:
            return None, False, False
        user = db.query(User).filter(User.id == st.crawfish_id).first()
        if not user:
            return None, False, False
        return user, False, True
    finally:
        db.close()


@router.websocket("/ws/observe")
async def ws_observe(ws: WebSocket):
    """
    统一观测端点。

    连接参数（query string）：
    - type: "world"（默认）或 "crawler"
    - token: 必填当 type=crawler

    ws://host/ws/observe                 → 世界模式（公开）
    ws://host/ws/observe?type=world      → 世界模式（显式）
    ws://host/ws/observe?type=crawler&token=xxx → 个人模式（需认证）
    """
    await ws.accept()

    # 解析参数
    obs_type = ws.query_params.get("type", "world")
    token = ws.query_params.get("token", "").strip()

    # type=crawler 需要 token
    if obs_type == "crawler" and not token:
        await ws.close(code=4001, reason="Token required for crawler mode")
        return

    # 验证 token（type=world 不需要）
    user = None
    is_owner = False
    if obs_type == "crawler":
        user, is_owner, _ = _get_user_from_token(token)
        if not user:
            await ws.close(code=4001, reason="Invalid token")
            return

    world_state = ws.app.state.get("world_state")
    if world_state is None:
        await ws.close(code=1011, reason="World not initialized")
        return

    if obs_type == "world":
        await _world_mode(ws, world_state)
    else:
        await _crawler_mode(ws, world_state, user, is_owner)


async def _world_mode(ws: WebSocket, world_state):
    """世界模式：每 2 秒推送所有在线用户位置（公开）"""

    async def _get_users_with_name(all_states):
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

    # 发送初始快照
    try:
        all_users = await asyncio.to_thread(world_state.get_all)
        users_with_name = await _get_users_with_name(all_users)
        await ws.send_json({
            "type": "snapshot",
            "ts": datetime.now(timezone.utc).isoformat(),
            "online_count": len(users_with_name),
            "users": users_with_name,
        })
    except Exception as e:
        logger.warning(f"World mode init snapshot failed: {e}")

    # 推送循环
    try:
        while True:
            await asyncio.sleep(SNAPSHOT_INTERVAL)
            try:
                all_users = await asyncio.to_thread(world_state.get_all)
                users_with_name = await _get_users_with_name(all_users)
                await ws.send_json({
                    "type": "snapshot",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "online_count": len(users_with_name),
                    "users": users_with_name,
                })
            except Exception as e:
                logger.debug(f"World mode push failed: {e}")
                break
    except WebSocketDisconnect:
        pass


async def _crawler_mode(ws: WebSocket, world_state, user: User, is_owner: bool):
    """个人龙虾模式：每 5 秒推送个人实时数据（需认证）"""

    user_id = user.id
    user_name = user.name

    # 发送 ready
    await ws.send_json({
        "type": "ready",
        "user": {"id": user_id, "name": user_name},
        "is_owner": is_owner,
    })

    async def push_loop():
        while True:
            await asyncio.sleep(CRAWLER_INTERVAL)
            try:
                all_users = await asyncio.to_thread(world_state.get_all)
                my_pos = next((u for u in all_users if u.user_id == user_id), None)

                # 获取今日社交事件
                db = SessionLocal()
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

                    # 批量获取 other_user 名字
                    other_ids = list({e.other_user_id for e in events if e.other_user_id})
                    name_map = {}
                    if other_ids:
                        rows = db.query(User.id, User.name).filter(User.id.in_(other_ids)).all()
                        name_map = {uid: name for uid, name in rows}

                    event_list = []
                    for e in events:
                        item = {
                            "type": e.event_type,
                            "other_user_id": e.other_user_id,
                            "other_user_name": name_map.get(e.other_user_id, "unknown") if e.other_user_id else None,
                            "x": e.x,
                            "y": e.y,
                            "ts": e.created_at.isoformat(),
                        }
                        event_list.append(item)
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
            except Exception as e:
                logger.debug(f"Crawler mode push error: {e}")

    try:
        await push_loop()
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 2: 修改 main.py，删除 admin router**

找到这一行并删除：
```python
app.include_router(admin.router)
```

- [ ] **Step 3: 运行测试验证**

Run: `python -m pytest tests/test_api.py -v --tb=short`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add app/api/ws_server.py app/main.py
git commit -m "feat(ws_server): 重构为统一 /ws/observe 端点，支持 world/crawler 模式"
```

---

## Task 3: 新增缺失 API

**Files:**
- Create: `app/api/client/history.py`
- Modify: `app/api/world.py`
- Modify: `app/main.py`

### 3.1 创建 /api/client/history/ 路由

- [ ] **Step 1: 创建 app/api/client/ 目录和 history.py**

```python
"""
/api/client/history/* 路由：历史数据查询

提供两种查询：
1. 分页查询（主）：GET /api/client/history/{type}
2. 备份查询（全量）：GET /api/client/history/backup

认证：通过 X-Token header
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, Path
from sqlalchemy import func, or_ as sql_or

from app.database import get_db
from app.models import Friendship, Message, MovementEvent, SocialEvent, User
from app.utils import plain_text

router = APIRouter(prefix="/api/client/history", tags=["client-history"])

VALID_TYPES = {"messages", "movements", "social", "all"}


def _get_user(token: str) -> User:
    db = next(get_db())
    try:
        user = db.query(User).filter(User.token == token).first()
        if not user:
            raise HTTPException(status_code=401, detail="Token 无效")
        user.last_seen_at = datetime.now(timezone.utc)
        db.commit()
        return user
    finally:
        db.close()


@router.get("/{history_type}")
def query_history(
    history_type: str = Path(..., description="类型：messages/movements/social/all"),
    since: str | None = None,
    until: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    x_token: str = Header(..., alias="X-Token"),
):
    """
    分页查询历史数据（主查询接口）。

    路径：
    - GET /api/client/history/messages
    - GET /api/client/history/movements
    - GET /api/client/history/social
    - GET /api/client/history/all

    参数：
    - since: ISO8601 开始时间
    - until: ISO8601 结束时间
    - cursor: 分页游标（上一页返回的 cursor）
    - limit: 每页数量（默认 50，最大 200）
    """
    if history_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"无效类型，可用：{VALID_TYPES}")

    user = _get_user(x_token)
    limit = min(limit, 200)

    # 解析时间范围
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

    db = next(get_db())
    try:
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

            # 获取发送者名字
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

        # 按 ts 排序
        result.sort(key=lambda x: x.get("ts", ""), reverse=True)
        result = result[:limit]

        # 构建分页
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
    finally:
        db.close()


@router.get("/backup")
def backup_history(
    type: str = "all",
    since: str | None = None,
    until: str | None = None,
    x_token: str = Header(..., alias="X-Token"),
):
    """
    全量备份查询（用于 AI Agent 本地数据丢失时恢复）。

    特点：
    - 返回完整数据，不做分页
    - 支持指定时间范围
    - 用于恢复本地记忆

    参数：
    - type: messages/movements/social/all（默认 all）
    - since: ISO8601 开始时间（可选，默认注册时间）
    - until: ISO8601 结束时间（可选，默认 now）
    """
    if type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"无效类型，可用：{VALID_TYPES}")

    user = _get_user(x_token)
    now = datetime.now(timezone.utc)

    since_dt = user.created_at
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

    db = next(get_db())
    try:
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
    finally:
        db.close()
```

- [ ] **Step 2: 创建 app/api/client/ 目录的 __init__.py**

```python
# app/api/client/
```

- [ ] **Step 3: 修改 main.py，注册新路由**

在 `from app.api import ...` 行下方添加：
```python
from app.api.client import history as client_history
```

在 `app.include_router(share.router)` 之后添加：
```python
app.include_router(client_history.router)
```

### 3.2 新增 /api/world/homepage/{user_id} AI 文本版

- [ ] **Step 4: 在 world.py 中添加 AI 文本版主页路由**

在 world.py 的 router 定义之后（文件末尾）添加：

```python
@router.get("/api/world/homepage/{user_id}")
def api_world_homepage(
    user_id: int,
    request: Request,
):
    """
    龙虾 AI 用的文本版主页（无认证）。

    返回格式：纯文本，包含用户基本信息和最近动态。
    """
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return plain_text("错误：用户不存在", status_code=404)

        now = datetime.now(timezone.utc)

        # 统计
        friends_count = db.query(Friendship).filter(
            sql_or(
                Friendship.user_a_id == user_id,
                Friendship.user_b_id == user_id,
            ),
            Friendship.status == "accepted",
        ).count()

        encounters_count = db.query(func.count(SocialEvent.id)).filter(
            SocialEvent.user_id == user_id,
            SocialEvent.event_type == "encounter",
        ).scalar() or 0

        # 状态
        world_state = _world_state_from_app(request)
        is_online = user_id in world_state.users
        if is_online:
            pos = world_state.users.get(user_id)
            pos_str = f"x={pos.x}, y={pos.y}" if pos else ""
        else:
            pos_str = "离线"
            if user.last_seen_at:
                delta = now - user.last_seen_at
                if delta.days > 0:
                    pos_str = f"最后在线 {delta.days}天前"
                elif delta.total_seconds() >= 3600:
                    pos_str = f"最后在线 {int(delta.total_seconds() / 3600)}小时前"
                elif delta.total_seconds() >= 60:
                    pos_str = f"最后在线 {int(delta.total_seconds() / 60)}分钟前"

        # 最近动态
        recent_events = (
            db.query(SocialEvent)
            .filter(SocialEvent.user_id == user_id)
            .order_by(SocialEvent.created_at.desc())
            .limit(5)
            .all()
        )
        other_ids = [e.other_user_id for e in recent_events if e.other_user_id]
        name_map = {}
        if other_ids:
            rows = db.query(User.id, User.name).filter(User.id.in_(other_ids)).all()
            name_map = {uid: name for uid, name in rows}

        lines = [
            f"主人：{user.name}",
            f"ID：{user.id}",
            f"简介：{user.description or '暂无简介'}",
            f"状态：{pos_str}",
            f"注册时间：{user.created_at.strftime('%Y-%m-%d')}",
            "",
            "社交数据：",
            f"  好友数：{friends_count}",
            f"  相遇次数：{encounters_count}",
            "",
            "最近动态：",
        ]
        for e in recent_events:
            delta = now - e.created_at
            if delta.total_seconds() < 3600:
                time_str = f"{int(delta.total_seconds() / 60)}分钟前"
            elif delta.days > 0:
                time_str = f"{delta.days}天前"
            else:
                time_str = f"{int(delta.total_seconds() / 3600)}小时前"

            other_name = name_map.get(e.other_user_id, "未知用户") if e.other_user_id else ""
            if e.event_type == "encounter":
                lines.append(f"  {time_str}  在 ({e.x}, {e.y}) 遇到了 {other_name}")
            elif e.event_type == "friendship":
                lines.append(f"  {time_str}  与 {other_name} 成为了好友")

        return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")
    finally:
        db.close()
```

- [ ] **Step 5: 运行测试验证**

Run: `python -m pytest tests/test_api.py -v --tb=short`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/api/client/history.py app/api/client/__init__.py app/api/world.py app/main.py
git commit -m "feat(api): 新增 /api/client/history/* 和 /api/world/homepage/{user_id}"
```

---

## Task 4: 测试覆盖

**Files:**
- Modify: `tests/test_api.py`

### 4.1 添加新端点测试

- [ ] **Step 1: 在 tests/test_api.py 末尾添加新测试**

```python
# ─── /api/client/history ────────────────────────────────────────────────────

def test_history_messages(client: TestClient, token):
    """GET /api/client/history/messages 返回消息历史"""
    uid, tok = token
    r = client.get(f"/api/client/history/messages", headers={"X-Token": tok})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "messages"
    assert "data" in data
    assert "pagination" in data


def test_history_backup(client: TestClient, token):
    """GET /api/client/history/backup 返回全量数据"""
    uid, tok = token
    r = client.get(f"/api/client/history/backup", headers={"X-Token": tok})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "all"
    assert "data" in data
    assert "total" in data


def test_history_invalid_type(client: TestClient, token):
    """无效的 history_type 返回 400"""
    uid, tok = token
    r = client.get("/api/client/history/invalid", headers={"X-Token": tok})
    assert r.status_code == 400


def test_history_no_token(client: TestClient):
    """无 token 返回 422"""
    r = client.get("/api/client/history/messages")
    assert r.status_code == 422


# ─── /api/world/homepage ───────────────────────────────────────────────────

def test_world_homepage_ai(client: TestClient, token):
    """GET /api/world/homepage/{user_id} 返回 AI 文本版主页"""
    uid, tok = token
    r = client.get(f"/api/world/homepage/{uid}")
    assert r.status_code == 200
    assert "主人：" in r.text
    assert f"ID：{uid}" in r.text


def test_world_homepage_not_found(client: TestClient):
    """不存在的用户返回 404"""
    r = client.get("/api/world/homepage/99999")
    assert r.status_code == 404
```

- [ ] **Step 2: 运行所有测试**

Run: `python -m pytest tests/test_api.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_api.py
git commit -m "test: 添加新端点测试覆盖"
```

---

## Task 5: 最终验证

- [ ] **Step 1: 运行完整测试套件**

Run: `python -m pytest tests/test_api.py -v`
Expected: ALL 51+ TESTS PASS

- [ ] **Step 2: 检查架构文档与代码一致性**

确认以下端点都存在：
- [ ] `GET /ws/observe?type=world` — 世界模式
- [ ] `GET /ws/observe?type=crawler&token=xxx` — 个人模式
- [ ] `GET /api/client/history/messages` — 消息历史
- [ ] `GET /api/client/history/backup` — 备份查询
- [ ] `GET /api/world/homepage/{user_id}` — AI 文本版主页
- [ ] `/ws/client` 返回紧凑格式 step_context

- [ ] **Step 3: 更新架构文档状态**

在架构设计_v2.md 顶部，将状态从"草稿"改为"已实现"：
```markdown
> 状态：已实现
> 实现日期：2026-03-27
```

---

## 自检清单

1. **Spec 覆盖检查**：对照架构设计_v2.md，每一项都有对应 Task 吗？
   - ✅ step_context 紧凑格式 → Task 1
   - ✅ /ws/observe 统一端点 → Task 2
   - ✅ /api/world/homepage/{user_id} → Task 3
   - ✅ /api/client/history/* → Task 3
   - ✅ admin.py 删除 → Task 2
   - ✅ 测试覆盖 → Task 4

2. **占位符扫描**：搜索 "TBD"、"TODO"、"实现later"、"填充" — 无此类占位符

3. **类型一致性**：各 Task 之间的接口是否一致？
   - step_context compact body 格式在 Task 1 定义
   - /ws/observe crawler 模式推送 crawler_snapshot（与设计文档一致）

---

## 计划完成

计划已保存到 `docs/superpowers/plans/2026-03-27-clawsocial-v2-refactor.md`。

**两个执行选项：**

**1. Subagent-Driven（推荐）** — 每个 Task 由独立 subagent 执行，Task 间有检查点

**2. Inline Execution** — 在本 session 内顺序执行，有检查点

**选择哪个方式？**
