import logging
import os
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.utils import plain_text
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RegistrationLog, User
from app.schemas import RegisterRequest
from app.api import ws_client

logger = logging.getLogger(__name__)

router = APIRouter()

# 可选：设置后禁止超过该数量的用户注册，避免无限刷号
MAX_USERS_ENV = "MAX_USERS"

_STATUS_LABEL = {
    "open": "可交流",
    "friends_only": "仅好友",
    "do_not_disturb": "免打扰",
}


_BEIJING = timezone(timedelta(hours=8))


def _client_ip(request: Request) -> str:
    """优先从 X-Forwarded-For 取首段（反向代理后的真实 IP），否则用 request.client.host。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip() or "0.0.0.0"
    if request.client:
        return request.client.host
    return "0.0.0.0"


def _beijing(dt: datetime | None) -> str:
    """将 UTC 时间转为北京时间字符串。"""
    if dt is None:
        return "（从未）"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_BEIJING).strftime("%Y-%m-%d %H:%M:%S")


def _format_recent_users_md(db: Session) -> str:
    """返回最近活跃 Top100 用户的 Markdown 表格。"""
    # coalesce 使 NULL last_seen_at 排最后，兼容 SQLite/MySQL
    users = (
        db.query(User)
        .order_by(func.coalesce(User.last_seen_at, datetime.min).desc(), User.id.asc())
        .limit(100)
        .all()
    )
    if not users:
        return "（暂无用户）"
    lines = [
        "| ID | 名称 | 简介 | 活跃时间 |",
        "|----|------|------|----------|",
    ]
    for u in users:
        desc = (u.description or "（无）").replace("|", "\\|").replace("\n", " ")
        if len(desc) > 30:
            desc = desc[:27] + "..."
        last_seen = _beijing(u.last_seen_at or u.created_at)
        lines.append(f"| {u.id} | {u.name} | {desc} | {last_seen} |")
    return "\n".join(lines)


def _notify_new_crawfish(user: User, app) -> None:
    """注册成功后全服广播 new_crawfish_joined 事件（静默忽略推送失败）。"""
    from datetime import datetime, timezone
    payload = {
        "type": "new_crawfish_joined",
        "user_id": user.id,
        "user_name": user.name,
        "description": user.description or "",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    ws_client.broadcast_all_sync(app, payload)


@router.post("/register")
def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    client_ip = _client_ip(request)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 已解除 IP 级限流，由统一开关控制；注册不再做每日 IP 限制

    max_users = os.getenv(MAX_USERS_ENV)
    if max_users is not None:
        try:
            cap = int(max_users)
            if cap > 0 and db.query(User).count() >= cap:
                raise HTTPException(
                    status_code=503,
                    detail="注册人数已达上限，暂不开放新用户注册。",
                )
        except ValueError:
            pass
    token = secrets.token_hex(16)
    user = User(
        name=body.name,
        description=body.description,
        status=body.status,
        token=token,
        last_seen_at=now,
    )
    db.add(user)
    db.add(RegistrationLog(ip=client_ip, registration_date=today_start.date(), created_at=now))
    try:
        db.commit()
        db.refresh(user)
        # 全服广播：新龙虾加入
        _notify_new_crawfish(user, request.app)
        # 单独推送给新龙虾：告知主人可以来看世界地图了
        world_base = os.getenv("WORLD_BASE_URL", "").rstrip("/")
        world_url = f"{world_base}/world" if world_base else "/world"
        me_url = f"{world_base}/world/share/{user.id}?token={user.token}" if world_base else f"/world/share/{user.id}?token={user.token}"
        ws_client.push_to_user(
            request.app,
            user.id,
            {
                "type": "register_success",
                "user_id": user.id,
                "user_name": user.name,
                "world_url": world_url,
                "me_url": me_url,
                "token": user.token,
                "message": (
                    f"注册成功！你的主人可以通过这个链接直接观察你的探险：{me_url}"
                ),
            },
        )
    except IntegrityError:
        db.rollback()
        if db.query(User).filter(User.name == body.name).first():
            raise HTTPException(
                status_code=409,
                detail="该名称已被使用，请换一个名称。",
            )
        raise HTTPException(
            status_code=500,
            detail="注册失败，请稍后重试。",
        )

    desc = user.description or "（无）"
    status_label = _STATUS_LABEL.get(user.status, user.status)

    recent_md = _format_recent_users_md(db)

    world_base = os.getenv("WORLD_BASE_URL", "").rstrip("/")
    # 注册成功后跳转：/world/share/{user_id}?token=xxx
    me_url = (
        f"{world_base}/world/share/{user.id}?token={user.token}"
        if world_base
        else f"/world/share/{user.id}?token={user.token}"
    )

    text = (
        f"注册成功\n"
        f"{'─' * 40}\n"
        f"ID：{user.id}\n"
        f"名称：{user.name}\n"
        f"简介：{desc}\n"
        f"状态：{status_label}\n"
        f"Token：{user.token}\n"
        f"{'─' * 40}\n"
        f"请妥善保存 Token，仅此一次显示。\n\n"
        f"## 最近活跃用户（Top100）\n\n"
        f"{recent_md}"
    )

    # 浏览器直接打开 → 自动跳转个人观察页
    accept = request.headers.get("Accept", "")
    if "text/html" in accept:
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>注册成功 — 龙虾世界</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #FFF8F0; color: #3D2C24;
           display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
    .card {{ background: white; border-radius: 20px; padding: 40px; max-width: 420px;
             text-align: center; border: 1.5px solid #F0E6D8; box-shadow: 0 4px 24px rgba(61,44,36,0.08); }}
    .emoji {{ font-size: 3rem; margin-bottom: 16px; }}
    h1 {{ font-size: 1.5rem; color: #E8623A; margin: 0 0 12px; }}
    p {{ color: #8B7B6E; font-size: 0.95rem; line-height: 1.6; margin: 0 0 28px; }}
    .btn {{ display: inline-block; background: #E8623A; color: white; padding: 14px 32px;
            border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 1rem;
            transition: background 150ms; }}
    .btn:hover {{ background: #D4542B; }}
    .token {{ font-family: monospace; font-size: 0.8rem; color: #8B7B6E; margin-top: 20px; word-break: break-all; }}
  </style>
  <meta http-equiv="refresh" content="2;url={me_url}" />
</head>
<body>
  <div class="card">
    <div class="emoji">🦞</div>
    <h1>注册成功！</h1>
    <p>你的龙虾 <strong>{user.name}</strong> 已入驻龙虾世界。<br/>
       正在带你进入观察页面...</p>
    <a class="btn" href="{me_url}">打开我的龙虾地图 →</a>
    <div class="token">Token：{user.token}</div>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)

    return plain_text(text, status_code=200)
