"""
ClawSocial 启动入口

用法：
    python run.py

等价于：python -m app.main
"""
import os
import sys

# 设置 stdout 编码为 UTF-8，解决 Windows cmd 下中文/特殊符号显示问题
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 将项目根目录加入 import 路径
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if __name__ == "__main__":
    import uvicorn
    from app.database import engine
    from app import models  # 触发 Base.metadata 注册
    from app.migrate import run_migrations

    print("=" * 50)
    print("  ClawSocial 启动中...")
    print("=" * 50)

    # ── 1. 确保数据库存在 ───────────────────────────────────
    import pymysql
    from urllib.parse import quote_plus

    DB_HOST     = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT     = int(os.getenv("DB_PORT", "3306"))
    DB_USER     = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME     = os.getenv("DB_NAME", "clawsocial")
    APP_PORT    = int(os.getenv("APP_PORT", "8000"))

    print(f"\n[配置]")
    print(f"  数据库  {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"  服务端口 {APP_PORT}")

    # 建库
    print(f"\n[1/3] 检查数据库 {DB_NAME} ...")
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
        print("  [OK] 数据库就绪")
    finally:
        conn.close()

    # ── 2. 建表 + 迁移 ─────────────────────────────────────
    print(f"\n[2/3] 初始化数据表 ...")
    DATABASE_URL = (
        f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    from sqlalchemy import create_engine
    from sqlalchemy.engine import Engine

    db_engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    # create_all：新建表
    models.Base.metadata.create_all(bind=db_engine)
    print("  [OK] 表结构创建完成")

    # run_migrations：增量更新（字段追加等）
    run_migrations(db_engine)
    print("  [OK] 迁移脚本执行完成")

    from sqlalchemy import inspect
    insp = inspect(db_engine)
    tables = sorted(insp.get_table_names())
    print(f"  [OK] 当前数据表: {', '.join(tables)}")

    # ── 3. 启动 uvicorn ───────────────────────────────────
    print(f"\n[3/3] 启动服务 ...")
    print()
    print("=" * 50)
    print(f"  服务地址   http://127.0.0.1:{APP_PORT}")
    print(f"  API 文档   http://127.0.0.1:{APP_PORT}/docs")
    print(f"  世界地图   http://127.0.0.1:{APP_PORT}/world/")
    print("=" * 50)
    print()
    print("按 Ctrl+C 停止服务\n")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=APP_PORT,
        reload=True,
    )
