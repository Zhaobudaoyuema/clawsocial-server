import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.logging_config import setup_logging

# ── 日志配置（入口处全局生效，所有模块的 logger.getLogger() 共享）─────────
setup_logging()
_root_logger = logging.getLogger(__name__)
# ────────────────────────────────────────────────────────────────────────

from app.database import engine, SessionLocal
from app.models import User
from app.utils import plain_text
from app import models
import importlib

importlib.import_module("app.models_deid")  # register deid tables with Base.metadata
from app.migrate import run_migrations
from app.api import blog, register, stats, world, ws_client, ws_server, ws_worker, share, deid, upload, drop, remote_command, remote_command_v11
from app.crawfish.social import friends, homepage, messages
from app.deid.worker.router import WorkerRouter
from app.deid.scan_queue import ScanQueue
from app.api.client import history as client_history
from app.crawfish.world.state import WorldConfig, WorldState
from app.uploads import UPLOADS_DIR

models.Base.metadata.create_all(bind=engine)
run_migrations(engine)


# 限流：由 RATE_LIMIT_ENABLED 控制，QPS 20，按 user_id 或 IP 统一限流

_RATE_LIMIT_EXEMPT = {"/health", "/stats"}


def _rate_limit_skip_path(path: str) -> bool:
    """官网静态资源与脱敏 API 不参与 QPS 限流（轮询/并行请求不应 429）。"""
    return (
        path.startswith("/assets/")
        or path.startswith("/world/assets/")
        or path.startswith("/api/deid")
        or path.startswith("/api/drop")
    )
_RATE_LIMIT_QPS = int(os.getenv("RATE_LIMIT_QPS", "20"))
_RATE_LIMIT_WINDOW_SEC = 1.0
_rate_limit_buckets: dict[str, list[float]] = {}  # key -> [timestamps]


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip() or "0.0.0.0"
    if request.client:
        return request.client.host
    return "0.0.0.0"


def _get_rate_limit_key(request: Request, x_token: str | None) -> str:
    """限流 key：有账号用 user_id，无账号用 IP，统一逻辑。"""
    if x_token:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.token == x_token).first()
            if user:
                return f"user:{user.id}"
        finally:
            db.close()
    return f"ip:{_client_ip(request)}"


def _check_rate_limit(request: Request, x_token: str | None) -> bool:
    """若超限返回 True（应拒绝），否则返回 False（放行）。QPS 限制。"""
    key = _get_rate_limit_key(request, x_token)
    now = time.monotonic()
    lst = _rate_limit_buckets.setdefault(key, [])
    cutoff = now - _RATE_LIMIT_WINDOW_SEC
    while lst and lst[0] < cutoff:
        lst.pop(0)
    if len(lst) >= _RATE_LIMIT_QPS:
        return True
    lst.append(now)
    return False
def _parse_rate_limit_enabled() -> bool:
    v = os.getenv("RATE_LIMIT_ENABLED", "1")
    return v.strip().lower() not in ("0", "false", "off", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    app.state.loop = asyncio.get_running_loop()
    app.state.ws_clients = {}  # /ws/client 连接池：user_id → WebSocket
    app.state.rate_limit_enabled = _parse_rate_limit_enabled()

    # WorldState starts empty — users are added when their /ws/client connects
    # and removed on disconnect. cleanup_inactive() handles any orphans.
    _world_state = WorldState(WorldConfig())
    app.state.world_state = _world_state

    from app.jobs.world_aggregator import start as start_scheduler, set_world_state
    from app.jobs.deid_cleanup import start as start_deid_cleanup

    set_world_state(_world_state)
    start_scheduler()
    start_deid_cleanup()

    from app.database import SessionLocal
    from app.deid.entity_types import ensure_default_entity_types
    from app.deid.settings_store import ensure_flow_prompts

    db = SessionLocal()
    try:
        ensure_flow_prompts(db)
        ensure_default_entity_types(db)
    finally:
        db.close()

    from app.deid.worker.relay_client import RemoteWorkerRelay, bootstrap_worker_relay

    app.state.worker_router = WorkerRouter()
    from app.remote_command import RemoteCommandRelay

    app.state.remote_command_relay = RemoteCommandRelay()
    remote_command_v11.app.state.remote_command_relay = RemoteCommandRelay()
    app.state.worker_relay = RemoteWorkerRelay()
    app.state.scan_queue = ScanQueue(app=app)
    await bootstrap_worker_relay(app.state.worker_relay)
    ping_task = asyncio.create_task(_worker_ping_loop(app))
    relay_status_task = asyncio.create_task(_relay_status_loop(app))
    remote_command_reset_task = asyncio.create_task(_remote_command_daily_reset_loop(app))

    yield

    ping_task.cancel()
    relay_status_task.cancel()
    remote_command_reset_task.cancel()
    for task in (ping_task, relay_status_task, remote_command_reset_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

    from app.jobs.deid_cleanup import stop as stop_deid_cleanup
    from app.jobs.world_aggregator import stop as stop_scheduler

    stop_deid_cleanup()
    stop_scheduler()


async def _worker_ping_loop(app: FastAPI) -> None:
    """Send heartbeat ping to Mac Worker every 30s."""
    import asyncio

    while True:
        await asyncio.sleep(30)
        router = getattr(app.state, "worker_router", None)
        if router:
            await router.send_ping()


async def _relay_status_loop(app: FastAPI) -> None:
    """Refresh remote worker status when local dev uses DEID_WORKER_RELAY_*."""
    import asyncio

    while True:
        relay = getattr(app.state, "worker_relay", None)
        if relay and relay.enabled:
            await relay.refresh_status()
        await asyncio.sleep(10)


def _seconds_until_next_remote_command_reset(now: datetime | None = None) -> float:
    tz = ZoneInfo(os.getenv("REMOTE_COMMAND_RESET_TIMEZONE", "Asia/Shanghai"))
    now = now.astimezone(tz) if now else datetime.now(tz)
    reset_at = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now >= reset_at:
        reset_at += timedelta(days=1)
    return max(0.0, (reset_at - now).total_seconds())


async def _remote_command_daily_reset_loop(app: FastAPI) -> None:
    """Clear all remote-command grants and WebSocket sessions at 04:00 Beijing time."""
    import asyncio

    while True:
        await asyncio.sleep(_seconds_until_next_remote_command_reset())
        for relay in (app.state.remote_command_relay, remote_command_v11.app.state.remote_command_relay):
            stats = await relay.clear_all(reason="daily_04_reset")
            _root_logger.warning("remote command daily reset cleared %s", stats)


app = FastAPI(lifespan=lifespan, title="ClawSocial Relay", version="2.0.0")

# 静态资源挂在 API 路由之前，避免被其它规则抢占；/world 子应用构建产物在 static/world/assets
_static_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_main_assets_dir = os.path.join(_static_root, "assets")
if os.path.isdir(_main_assets_dir):
    app.mount(
        "/assets",
        StaticFiles(directory=_main_assets_dir, html=False),
        name="website_assets",
    )
_world_assets_dir = os.path.join(_static_root, "world", "assets")
if os.path.isdir(_world_assets_dir):
    app.mount(
        "/world/assets",
        StaticFiles(directory=_world_assets_dir, html=False),
        name="world_website_assets",
    )

_DEID_ACCESS_EXEMPT = {"/api/deid/access/verify"}


@app.middleware("http")
async def deid_access_middleware(request: Request, call_next):
    if os.getenv("TESTING"):
        return await call_next(request)
    path = request.scope.get("path", "").split("?")[0]
    if path.startswith("/api/deid") and not path.startswith("/api/deid/dev"):
        if path not in _DEID_ACCESS_EXEMPT:
            from app.deid.access_token import validate_deid_access_session

            token = request.headers.get("X-Deid-Access-Token") or request.query_params.get(
                "access_token"
            )
            if not validate_deid_access_session(token):
                return plain_text("错误 401：需要有效的访问口令", status_code=401)
    return await call_next(request)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if os.getenv("TESTING"):
        return await call_next(request)
    path = request.scope.get("path", "")
    if path in _RATE_LIMIT_EXEMPT or _rate_limit_skip_path(path):
        return await call_next(request)
    enabled = getattr(request.app.state, "rate_limit_enabled", True)
    if not enabled:
        return await call_next(request)
    x_token = request.headers.get("X-Token")
    if _check_rate_limit(request, x_token):
        return plain_text("错误：请求过于频繁，请稍后再试。", status_code=429)
    return await call_next(request)


_PLAIN_TEXT_ONLY_PATHS = _RATE_LIMIT_EXEMPT


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith('/api/gomoku/'):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})
    from fastapi.responses import JSONResponse

    path = request.scope.get("path", "").split("?")[0]
    if path.startswith("/api/deid/dev") or path.startswith("/api/remote-command"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    # /api/drop 返回 JSON 格式错误，保留原始 HTTP 状态码
    if path.startswith("/api/drop"):
        return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": exc.detail})
    if path in _PLAIN_TEXT_ONLY_PATHS:
        return plain_text(f"错误 {exc.status_code}：{exc.detail}", status_code=exc.status_code)
    # "Not Found" is the default 404 message — pass through real status code
    return plain_text(f"错误 {exc.status_code}：{exc.detail}", status_code=404 if exc.status_code == 404 else 200)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith('/api/gomoku/'):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={'detail': '请求参数格式不正确'})
    errors = "; ".join(
        f"{' -> '.join(str(l) for l in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )
    path = request.scope.get("path", "").split("?")[0]
    if path.startswith("/api/remote-command"):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": exc.errors()})
    if path in _PLAIN_TEXT_ONLY_PATHS:
        return plain_text(f"请求格式错误：{errors}", status_code=422)
    return plain_text(f"请求格式错误：{errors}", status_code=200)


@app.get("/health")
def health():
    """轻量存活探测，可用于负载均衡/探活。"""
    return {"status": "ok"}


from app.api import gomoku
app.include_router(gomoku.router)

app.include_router(register.router)
app.include_router(stats.router)
app.include_router(world.router)
app.include_router(ws_client.router)
app.include_router(ws_server.router)
app.include_router(share.router)
app.include_router(client_history.router)
app.include_router(blog.router)
app.include_router(deid.router)
app.include_router(ws_worker.router)
app.include_router(remote_command.router)
app.include_router(remote_command.ws_router)
app.mount("/legacy-v11", remote_command_v11.app)
app.include_router(upload.router)
app.include_router(friends.router)
app.include_router(homepage.router)
app.include_router(messages.router)
app.include_router(drop.router)

from app.api.deid_dev import include_dev_relay_routes

include_dev_relay_routes(app)

# 官网（Vue SPA 构建产物）
@app.get("/")
async def serve_website():
    """ClawSocial 官网首页"""
    from fastapi.responses import FileResponse
    import os
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(path)


# ── Vue SPA 前端路由 ─────────────────────────────────────────────────────────
# 使用显式路由，避免与 API 路由冲突（API 404 由 FastAPI 自然处理）

@app.get("/world")
@app.get("/world/")
async def serve_world():
    """世界地图页"""
    from fastapi.responses import FileResponse
    import os
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))


@app.get("/world/me")
@app.get("/world/me/")
async def serve_crawler():
    """我的虾页"""
    from fastapi.responses import FileResponse
    import os
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))


@app.get("/home")
@app.get("/home/")
async def serve_home():
    """龙虾社交世界介绍页"""
    from fastapi.responses import FileResponse
    import os
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))


@app.get("/blog")
@app.get("/blog/")
async def serve_blog():
    """博客文章页"""
    from fastapi.responses import FileResponse
    import os
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))


@app.get("/deid")
@app.get("/deid/")
async def serve_deid():
    """财务文档脱敏工具"""
    from fastapi.responses import FileResponse
    import os
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))


@app.get("/drop")
@app.get("/drop/")
async def serve_drop():
    """文件投递页"""
    from fastapi.responses import FileResponse
    import os
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html"))


# ── 用户上传文件静态服务 ───────────────────────────────────────────────────────
# 必须放在所有 API 路由之后，避免 /files 与 API 路径冲突
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/files",
    StaticFiles(directory=str(UPLOADS_DIR), html=False),
    name="user_uploads",
)


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )
