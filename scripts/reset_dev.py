#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键重置 ClawSocial 开发数据库：清空所有数据，从零开始。

用法:
    python scripts/reset_dev.py          # 使用 .env MySQL 配置
    python scripts/reset_dev.py --sqlite  # 使用 SQLite（无需 MySQL）
    python scripts/reset_dev.py --dry-run # 打印计划，不执行

--dry-run 模式无需数据库连接，直接显示将要执行的操作。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ── resolve project root ──────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Reset ClawSocial dev database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sqlite",
        action="store_true",
        help="Force SQLite mode (ignores .env MySQL config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without connecting to DB",
    )
    parser.add_argument(
        "--uploads-dir",
        default=None,
        help="Uploads directory to clear (default: from UPLOADS_DIR env or ./uploads/)",
    )
    return parser.parse_args()


# ── helpers ─────────────────────────────────────────────────────────────────
def log(msg: str):
    print(f"  {msg}")


def log_ok(msg: str):
    print(f"  [OK] {msg}")


def log_warn(msg: str):
    print(f"  [WARN] {msg}")


def log_skip(msg: str):
    print(f"  [SKIP] {msg}")


# ── MySQL ────────────────────────────────────────────────────────────────────
def mysql_info() -> tuple[str, str, str, str, str]:
    """Return (db_url, host, port, db_name, username) from .env."""
    from dotenv import load_dotenv
    from urllib.parse import quote_plus

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "relay")
    password = os.getenv("DB_PASSWORD", "relaypass")
    name = os.getenv("DB_NAME", "clawsocial")
    db_url = (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}?charset=utf8mb4"
    )
    return db_url, host, port, name, user


def reset_mysql(dry_run: bool):
    db_url, host, port, db_name, user = mysql_info()

    print(f"  Host:     {host}:{port}")
    print(f"  Database: {db_name}")
    print(f"  User:     {user}")

    if dry_run:
        log_ok("Would DROP DATABASE IF EXISTS")
        log_ok("Would CREATE DATABASE")
        log_ok("Would run: pytest tests/test_api.py -q")
        return

    from sqlalchemy import create_engine, text
    from app.database import Base
    from app.migrate import run_migrations

    # Connect WITHOUT database name (root connection) to create/drop DB
    from urllib.parse import quote_plus
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    root_password = os.getenv("DB_PASSWORD", "relaypass")
    root_url = (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(root_password)}"
        f"@{host}:{port}/?charset=utf8mb4"
    )

    root_engine = create_engine(root_url, isolation_level="AUTOCOMMIT")
    try:
        with root_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS `{db_name}`"))
            conn.execute(
                text(
                    f"CREATE DATABASE `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        root_engine.dispose()
    log_ok(f"DROP + CREATE DATABASE `{db_name}`")

    # Now connect to the fresh DB and create tables
    app_engine = create_engine(db_url, pool_pre_ping=True, pool_size=5, max_overflow=3)
    Base.metadata.create_all(bind=app_engine)
    run_migrations(app_engine)
    app_engine.dispose()
    log_ok("Created all tables and ran migrations")


# ── SQLite ──────────────────────────────────────────────────────────────────
SQLITE_DEFAULT_PATH = PROJECT_ROOT / "clawsocial.db"


def reset_sqlite(dry_run: bool):
    db_path = SQLITE_DEFAULT_PATH

    print(f"  DB file: {db_path}")
    if db_path.exists():
        size = db_path.stat().st_size
        print(f"  Size:    {size:,} bytes")
    else:
        print(f"  Size:    (file does not exist)")

    if dry_run:
        log_ok("Would delete SQLite DB file")
        log_ok("Would run Base.metadata.create_all() + migrations")
        log_ok("Would run: pytest tests/test_api.py -q")
        return

    from sqlalchemy import create_engine
    from app.database import Base
    from app.migrate import run_migrations

    if db_path.exists():
        db_path.unlink()
        log_ok(f"Deleted {db_path}")
    else:
        log_skip("No existing DB file to delete")

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    engine.dispose()
    log_ok("Created all tables and ran migrations")


# ── uploads ──────────────────────────────────────────────────────────────────
def clear_uploads(dry_run: bool, uploads_dir_arg: str | None):
    if uploads_dir_arg:
        uploads = Path(uploads_dir_arg)
    else:
        uploads = Path(os.getenv("UPLOADS_DIR", PROJECT_ROOT / "uploads"))

    print(f"  Uploads: {uploads}")

    if not uploads.exists():
        log_skip("Directory does not exist")
        return

    files = [f for f in uploads.rglob("*") if f.is_file()]
    if not files:
        log_ok("Already empty")
        return

    size = sum(f.stat().st_size for f in files)
    print(f"  Files:   {len(files)} ({size:,} bytes)")

    if dry_run:
        log_ok(f"Would delete {len(files)} file(s)")
        return

    for f in files:
        f.unlink()
    log_ok(f"Deleted {len(files)} file(s)")


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    # Windows console: force UTF-8 output so Chinese chars print correctly
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # For --sqlite mode, set TESTING=1 so that app.database creates an in-memory
    # SQLite engine instead of trying to connect to MySQL (which may not exist).
    if args.sqlite:
        os.environ["TESTING"] = "1"

    divider = "=" * 58
    mode = "SQLite" if args.sqlite else "MySQL"
    dry_label = "[DRY-RUN] " if args.dry_run else ""

    print(f"\n{divider}")
    print(f"{dry_label}ClawSocial 数据库重置")
    print(f"{divider}\n")
    print(f"  模式: {mode}")

    if args.sqlite:
        reset_sqlite(args.dry_run)
    else:
        try:
            reset_mysql(args.dry_run)
        except Exception as exc:
            print(f"  [FAIL] MySQL 连接失败: {exc}")
            print(f"  提示: 使用 --sqlite 模式无需 MySQL:")
            print(f"          python scripts/reset_dev.py --sqlite")
            sys.exit(1)

    print()
    clear_uploads(args.dry_run, args.uploads_dir)

    print(f"\n{divider}")
    print(f"{dry_label}重置完成")
    print(f"{divider}\n")


if __name__ == "__main__":
    main()
