"""
ClawSocial 日志系统

三档日志架构：
  1. logs/app.log               — 主日志：系统启动/连接摘要/scheduler/异常
  2. logs/client/<conn_file>.log — per-connection 实时日志（收到/返回/推送）
  3. logs/archive/<date>/        — 断开后归档（.log）

方向语义：
  [→ recv]  收到客户端消息
  [← send]  服务端响应消息
  [↑ push]  服务端主动推送
"""
import logging
import os
import shutil
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.time_utils import now_beijing


# ── 全局路径常量（相对于项目根目录）───────────────────────────────────────

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR       = os.path.join(_ROOT, "logs")
CLIENT_LOG_DIR = os.path.join(LOGS_DIR, "client")
ARCHIVE_DIR    = os.path.join(LOGS_DIR, "archive")
APP_TRACE_MAX_LEN = int(os.getenv("APP_TRACE_MAX_LEN", "2000"))
APP_TRACE_PUSH_SUMMARY_THRESHOLD = int(os.getenv("APP_TRACE_PUSH_SUMMARY_THRESHOLD", "2500"))


# ── 基础格式化工具 ────────────────────────────────────────────────────────

def _safe_json(d: dict[str, Any] | None, max_len: int = 500) -> str:
    """将 dict 序列化为 JSON 字符串，超长截断。"""
    if d is None:
        return "{}"
    import json
    s = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    if len(s) > max_len:
        s = s[:max_len] + f'...(+{len(s)-max_len} chars)'
    return s


# ── 方向标签常量 ──────────────────────────────────────────────────────────

class Dir:
    RECV = "→ recv"    # 收到客户端消息
    SEND = "← send"    # 服务端响应
    PUSH = "↑ push"   # 服务端主动推送


# ── 主日志 logger ─────────────────────────────────────────────────────────

_app_logger: logging.Logger | None = None


def get_app_logger() -> logging.Logger:
    """返回主日志 logger（必须在 setup_logging() 之后调用）。"""
    if _app_logger is None:
        return logging.getLogger("clawsocial")
    return _app_logger


def _fmt_ts() -> str:
    return now_beijing().strftime("%Y-%m-%d %H:%M:%S")


# ── ClientLogger ──────────────────────────────────────────────────────────

class ClientLogger:
    """
    每个 WebSocket 连接对应一个实例。

    写入两个 handler：
      - 主日志（app.log）  → 连接/断开摘要
      - 子目录日志文件     → 全量双向消息

    断开时 close() 自动归档为 .log 文件（不压缩）。

    log_subdir: 子目录名，默认 "client"（/ws/client 用）；
                "observe" 则写入 logs/observe/（/ws/observe 用）。
    """

    def __init__(
        self,
        user_id: int | None,
        user_name: str,
        conn_id: str,
        client_addr: str = "",
        log_subdir: str = "client",
    ):
        self.user_id     = user_id
        self.user_name   = user_name
        self.conn_id     = conn_id
        self.client_addr = client_addr
        self._started_at = time.monotonic()
        self.log_subdir = log_subdir

        # 干净的文件名（IP 地址保留 . 不替换）
        safe_name = "".join(c if c.isalnum() else "_" for c in user_name)
        if self.user_id:
            fname = f"uid{self.user_id}_{safe_name}_{conn_id}.log"
        else:
            fname = f"observe_{safe_name}_{conn_id}.log"

        subdir = os.path.join(LOGS_DIR, log_subdir)
        os.makedirs(subdir, exist_ok=True)
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

        self._client_path = os.path.join(subdir, fname)

        # client 文件 handler
        self._fh: RotatingFileHandler | None = None
        try:
            self._fh = RotatingFileHandler(
                self._client_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=0,          # 不在本文件轮转，归档时整文件压缩
                encoding="utf-8",
            )
            self._fh.setFormatter(logging.Formatter("%(message)s"))
        except OSError as exc:
            self._fh = None
            logging.warning("[ClientLogger] 无法创建 client log 文件 %s: %s", self._client_path, exc)

        # 连接时立即写主日志
        self.app_log(
            f"[CONN] uid={self.user_id} name={self.user_name!r} "
            f"addr={self.client_addr} conn_id={self.conn_id}"
        )

    # ── 主日志（写入 app.log）─────────────────────────────────────────────

    def app_log(self, msg: str, level: str = "INFO") -> None:
        """写主日志（连接摘要 / 断开记录 / 异常）。"""
        lg = get_app_logger()
        getattr(lg, level.lower(), lg.info)(msg)

    # ── client 日志（写入 logs/client/<file>.log）──────────────────────────

    def _client_write(self, direction: str, type_: str, payload: dict | None) -> None:
        if self._fh is None:
            return
        prefix = f"{_fmt_ts()} [{self._uid_tag()}] [{direction}] {type_}"
        body   = _safe_json(payload) if payload else ""
        line   = f"{prefix}  {body}"
        self._fh.emit(logging.LogRecord(
            name="clawsocial.client",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=line,
            args=(),
            exc_info=None,
        ))

    def _sanitized_payload(self, payload: dict | None) -> dict | None:
        if not payload:
            return payload
        redacted = dict(payload)
        for k in ("token", "x_token"):
            if k in redacted:
                redacted[k] = "***"
        return redacted

    def _app_payload(self, direction: str, msg_type: str, payload: dict | None) -> dict | None:
        sanitized = self._sanitized_payload(payload)
        if direction == Dir.PUSH and isinstance(sanitized, dict):
            preview = _safe_json(sanitized, max_len=APP_TRACE_PUSH_SUMMARY_THRESHOLD + 200)
            if len(preview) > APP_TRACE_PUSH_SUMMARY_THRESHOLD:
                return {
                    "_summary": "payload truncated for app.log",
                    "type": msg_type,
                    "keys": list(sanitized.keys())[:20],
                    "size": len(preview),
                }
        return sanitized

    def _app_trace(self, direction: str, msg_type: str, payload: dict | None) -> None:
        if self.log_subdir == "observe":
            # Keep app.log focused on ws/client traffic; observe(UI) traces stay in per-connection logs.
            return
        body = _safe_json(self._app_payload(direction, msg_type, payload), max_len=APP_TRACE_MAX_LEN)
        self.app_log(f"[TRACE] [{self._uid_tag()}] [{direction}] {msg_type}  {body}")

    def _uid_tag(self) -> str:
        if self.user_id:
            return f"uid={self.user_id} {self.user_name!r}"
        return f"{self.user_name!r}"

    # ── 公开日志方法 ──────────────────────────────────────────────────────

    def recv(self, msg_type: str, payload: dict) -> None:
        """[→ recv] 记录收到客户端消息。"""
        self._client_write(Dir.RECV, msg_type, payload)
        self._app_trace(Dir.RECV, msg_type, payload)

    def send(self, msg_type: str, payload: dict) -> None:
        """[← send] 记录服务端响应。"""
        self._client_write(Dir.SEND, msg_type, payload)
        self._app_trace(Dir.SEND, msg_type, payload)

    def push(self, msg_type: str, payload: dict) -> None:
        """[↑ push] 记录服务端主动推送。"""
        self._client_write(Dir.PUSH, msg_type, payload)
        self._app_trace(Dir.PUSH, msg_type, payload)

    # ── 关闭 & 归档 ────────────────────────────────────────────────────────

    def close(self, reason: str = "disconnect") -> None:
        """关闭文件 handler 并归档为 .log。"""
        duration_s = int(time.monotonic() - self._started_at)

        if self._fh:
            self._fh.close()
            self._fh = None

        # 归档：保持子目录结构 logs/archive/{date}/client/... 或 observe/...（纯 .log）
        if os.path.exists(self._client_path):
            try:
                date_str       = now_beijing().strftime("%Y-%m-%d")
                archive_subdir = os.path.join(ARCHIVE_DIR, date_str, os.path.dirname(self._client_path).split(os.path.sep)[-1])
                os.makedirs(archive_subdir, exist_ok=True)
                archive_path   = os.path.join(archive_subdir, os.path.basename(self._client_path))
                if os.path.exists(archive_path):
                    stem, ext = os.path.splitext(archive_path)
                    archive_path = f"{stem}_{int(time.time())}{ext}"
                shutil.move(self._client_path, archive_path)
                archive_note = f" archived to {archive_path}"
            except Exception as exc:
                archive_note = f" archive FAILED: {exc}"
        else:
            archive_note = " (file not found)"

        self.app_log(
            f"[DISCONN] uid={self.user_id} name={self.user_name!r} "
            f"conn_id={self.conn_id} reason={reason} duration={duration_s}s{archive_note}"
        )


# ── 全局日志初始化 ────────────────────────────────────────────────────────

def setup_logging() -> None:
    """
    一次性配置全局日志：
      - logs/app.log   （RotatingFileHandler，10MB，5个备份）
      - logs/client/   目录
      - logs/archive/  目录
      - 统一 uvicorn / apscheduler 日志级别
    """
    global _app_logger

    log_level     = os.getenv("LOG_LEVEL", "INFO").upper()
    uvicorn_level = os.getenv("UVICORN_LOG_LEVEL", "INFO").upper()

    # 目录
    os.makedirs(LOGS_DIR,       exist_ok=True)
    os.makedirs(CLIENT_LOG_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR,    exist_ok=True)

    # 主日志 handler（app.log）
    app_handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # stderr handler（始终输出到控制台）
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(app_handler.formatter)

    # 全局 root logger
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.handlers.clear()
    root.addHandler(app_handler)
    root.addHandler(console_handler)

    # uvicorn 日志
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access",
                 "uvicorn.asgi", "uvicorn.protocol",
                 "uvicorn.protocol.http", "uvicorn.protocol.websockets"):
        lg = logging.getLogger(name)
        lg.setLevel(getattr(logging, uvicorn_level, logging.INFO))
        lg.handlers.clear()
        lg.addHandler(app_handler)
        lg.addHandler(console_handler)

    # apscheduler 日志（降低噪音）
    for name in ("apscheduler", "apscheduler.executors", "apscheduler.scheduler"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)

    _app_logger = logging.getLogger("clawsocial")
    _app_logger.setLevel(getattr(logging, log_level, logging.INFO))


def new_conn_id() -> str:
    """生成 8 位唯一连接 ID（用于文件名）。"""
    return uuid.uuid4().hex[:8]
