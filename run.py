"""
ClawSocial 启动入口

用法：
    python run.py
"""
import logging
import os
import signal
import sys
import subprocess
import time

# Windows 下启用 UTF-8 模式
os.environ.setdefault("PYTHONUTF8", "1")

# 项目根目录加入 import 路径
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.logging_config import setup_logging

setup_logging()
_logger = logging.getLogger(__name__)


def _kill_port(port):
    """强制终止占用指定端口的 Windows 进程。
    使用 netstat 代替 PowerShell，避免在 Git Bash / MSYS2 环境下 PowerShell 挂起。
    """
    _CMD_TIMEOUT = 10
    try:
        # 用 netstat 查找监听端口的 PID（比 PowerShell 快得多，兼容性好）
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_CMD_TIMEOUT,
        )
        pids = set()
        for line in result.stdout.splitlines():
            # 匹配 "TCP  0.0.0.0:8000 ... LISTENING  1234" 或 "[::]:8000"
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1].strip()
                if pid.isdigit() and pid != "0":
                    pids.add(pid)

        if not pids:
            return

        for pid in pids:
            _logger.info("  终止旧进程 PID=%s (占用端口 %s)", pid, port)
            kr = subprocess.run(
                ["taskkill", "/F", "/PID", pid],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=_CMD_TIMEOUT,
            )
            if kr.returncode != 0:
                _logger.warning("  taskkill 失败 PID=%s: %s", pid, kr.stderr.strip())
            else:
                _logger.info("  已终止 PID=%s", pid)
    except subprocess.TimeoutExpired:
        _logger.warning("  清理端口 %s 超时，跳过", port)
    except Exception as e:
        _logger.warning("  清理端口 %s 时出错（可忽略）: %s", port, e)


if __name__ == "__main__":
    import uvicorn
    import pymysql
    from urllib.parse import quote_plus

    from app import models
    from app.migrate import run_migrations

    _logger.info("=" * 50)
    _logger.info("  ClawSocial 启动中...")
    _logger.info("=" * 50)

    # ── 0. 清理旧进程（确保端口不受占用）────────────────────
    APP_PORT = 8000
    DB_HOST  = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT  = int(os.getenv("DB_PORT", "3306"))
    DB_USER  = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME  = os.getenv("DB_NAME", "clawsocial")

    _logger.info("[配置]  数据库  %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
    _logger.info("[配置]  服务端口 %s", APP_PORT)

    _logger.info("[0/4] 清理旧进程 ...")
    _kill_port(APP_PORT)
    time.sleep(0.5)
    _logger.info("  [OK] 端口已清空")

    # ── 1. 确保数据库存在 ────────────────────────────────
    _logger.info("[1/4] 检查数据库 %s ...", DB_NAME)
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD, charset="utf8mb4"
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"
                f" CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        _logger.info("  [OK] 数据库就绪")
    finally:
        conn.close()

    # ── 2. 建表 + 迁移 ────────────────────────────────
    _logger.info("[2/4] 初始化数据表 ...")
    DATABASE_URL = (
        f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    from sqlalchemy import create_engine, inspect
    db_engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    models.Base.metadata.create_all(bind=db_engine)
    _logger.info("  [OK] 表结构创建完成")

    run_migrations(db_engine)
    _logger.info("  [OK] 迁移脚本执行完成")

    tables = sorted(inspect(db_engine).get_table_names())
    _logger.info("  [OK] 当前数据表: %s", ", ".join(tables))

    # ── 3. 清理旧进程（建表后再次确认端口空闲）──────────────
    _logger.info("[3/4] 再次清理旧进程（确保干净）...")
    _kill_port(APP_PORT)
    time.sleep(0.5)
    _logger.info("  [OK] 端口已清空")

    # ── 4. 启动 uvicorn ───────────────────────────────
    _logger.info("[4/4] 启动服务 ...")
    _logger.info("=" * 50)
    _logger.info("  服务地址   http://127.0.0.1:%s", APP_PORT)
    _logger.info("  API 文档   http://127.0.0.1:%s/docs", APP_PORT)
    _logger.info("  世界地图   http://127.0.0.1:%s/world/", APP_PORT)
    _logger.info("=" * 50)
    _logger.info("按 Ctrl+C 停止服务")

    server = uvicorn.Server(
        config=uvicorn.Config(
            "app.main:app",
            host="0.0.0.0",
            port=APP_PORT,
            reload=False,
            log_level="info",
            access_log=False,
        )
    )

    # Ctrl+C 优雅退出
    def handle_sigterm(signum, frame):
        _logger.info("收到 Ctrl+C，正在停止服务...")
        server.should_exit = True

    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)

    server.run()
