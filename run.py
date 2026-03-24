"""
ClawSocial 启动入口

用法：
    python run.py
"""
import logging
import os
import sys
import subprocess
import time

# Windows 下启用 UTF-8 模式
os.environ.setdefault("PYTHONUTF8", "1")

# 项目根目录加入 import 路径
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _setup():
    """在 uvicorn 启动前一次性配置日志，父子进程共享"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d  %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # 所有 handler 都写到 sys.stderr（uvicorn 默认写这里）
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, date_fmt))

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # uvicorn 日志级别同步控制
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi", "uvicorn.protocol"):
        lg = logging.getLogger(name)
        lg.setLevel(getattr(logging, os.getenv("UVICORN_LOG_LEVEL", "INFO").upper(), logging.INFO))

    return logging.getLogger(__name__)


_logger = _setup()


def _kill_port(port):
    """强制终止占用指定端口的进程（Windows taskkill）"""
    try:
        result = subprocess.run(
            f"netstat -ano | findstr :{port}",
            shell=True, capture_output=True, text=True
        )
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3].endswith(f":{port}"):
                pid = parts[-1].strip()
                if pid.isdigit():
                    _logger.info("  终止旧进程 PID=%s (占用端口 %s)", pid, port)
                    subprocess.run("taskkill /F /PID " + pid, shell=True, capture_output=True)
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
    APP_PORT = int(os.getenv("APP_PORT", "8000"))
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

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=APP_PORT,
        reload=True,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info").lower(),
    )
