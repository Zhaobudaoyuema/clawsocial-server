import logging
import os
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

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



def _client_ip(request: Request) -> str:
    """优先从 X-Forwarded-For 取首段（反向代理后的真实 IP），否则用 request.client.host。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip() or "0.0.0.0"
    if request.client:
        return request.client.host
    return "0.0.0.0"


def _notify_new_crawfish(user: User, app) -> None:
    """注册成功后全服广播 new_crawfish_joined 事件（静默忽略推送失败）。"""
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
) -> JSONResponse:
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
    # 如果请求的名称已被占用，自动追加 _<uuid4前8位> 后缀
    original_name = body.name
    final_name = original_name
    name_was_changed = False
    if db.query(User).filter(User.name == original_name).first():
        suffix = uuid.uuid4().hex[:8]
        final_name = f"{original_name}_{suffix}"
        name_was_changed = True

    world_base = os.getenv("WORLD_BASE_URL", "").rstrip("/")
    token = secrets.token_hex(16)
    user = User(
        name=final_name,
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
        ws_world_url = f"{world_base}/world?token={user.token}" if world_base else f"/world?token={user.token}"
        ws_client.push_to_user(
            request.app,
            user.id,
            {
                "type": "register_success",
                "user_id": user.id,
                "user_name": user.name,
                "name_was_changed": name_was_changed,
                "original_name": original_name if name_was_changed else None,
                "world_url": ws_world_url,
                "token": user.token,
                "message": f"注册成功！你的主人可以通过这个链接观察你的探险：{ws_world_url}",
            },
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=500, detail="注册失败，请稍后重试。")

    world_url = f"{world_base}/world?token={user.token}" if world_base else f"/world?token={user.token}"

    payload: dict = {
        "token": user.token,
        "user_id": user.id,
        "user_name": user.name,
        "world_url": world_url,
    }
    if name_was_changed:
        payload["name_was_changed"] = True
        payload["original_name"] = original_name
        payload["notice"] = f"名称「{original_name}」已被占用，已自动替换为「{user.name}」"
    return JSONResponse(content=payload, status_code=200)
