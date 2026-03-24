"""
World 热力聚合 + 数据清理 APScheduler 任务

聚合任务（每5分钟）：
  movement_events  →  heatmap_cells
  按 cell_x = x // 30, cell_y = y // 30 分桶，COUNT 后 UPSERT。

清理任务（每日）：
  90 天前 movement_events + social_events → DELETE。

使用 run_migration / auto-flush 时，任务中途失败不影响数据完整性。
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func, text

from app.database import SessionLocal
from app.models import MovementEvent

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")

CELL_SIZE = 30  # 与 WorldState.CELL_SIZE 保持一致
TTL_DAYS = 90


def _agg_cells():
    """
    从 movement_events 聚合到 heatmap_cells。
    按 (cell_x, cell_y) 分桶，UPSERT event_count。

    使用 func.floor() 确保整数除法，兼容 MySQL 和 SQLite。
    UPSERT 使用 INSERT ... ON DUPLICATE KEY UPDATE（MySQL 语法），
    通过检测 dialect 自适应：MySQL 用原生 UPSERT，SQLite 用 REPLACE。
    """
    db = SessionLocal()
    dialect = db.bind.dialect.name if db.bind else "mysql"
    try:
        # 聚合最近 10 分钟未处理的 movement_events
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        rows = (
            db.query(
                func.floor(MovementEvent.x / CELL_SIZE).label("cell_x"),
                func.floor(MovementEvent.y / CELL_SIZE).label("cell_y"),
                func.count().label("cnt"),
            )
            .filter(MovementEvent.created_at >= cutoff)
            .group_by(
                func.floor(MovementEvent.x / CELL_SIZE),
                func.floor(MovementEvent.y / CELL_SIZE),
            )
            .all()
        )

        if not rows:
            return 0

        now = datetime.now(timezone.utc)
        for row in rows:
            cx = int(row.cell_x)
            cy = int(row.cell_y)
            if dialect == "sqlite":
                # SQLite: INSERT OR IGNORE ensures new cells are inserted with event_count=0,
                # then UPDATE adds the batch count. Existing cells are silently skipped by
                # IGNORE so UPDATE can safely increment them.
                db.execute(
                    text("""
                        INSERT OR IGNORE INTO heatmap_cells (cell_x, cell_y, event_count, updated_at)
                        VALUES (:cx, :cy, 0, :now)
                    """),
                    {"cx": cx, "cy": cy, "now": now},
                )
                db.execute(
                    text("""
                        UPDATE heatmap_cells
                        SET event_count = event_count + :inc,
                            updated_at = :now
                        WHERE cell_x = :cx AND cell_y = :cy
                    """),
                    {"cx": cx, "cy": cy, "inc": row.cnt, "now": now},
                )
            else:
                # MySQL / 默认: ON DUPLICATE KEY UPDATE
                db.execute(
                    text("""
                        INSERT INTO heatmap_cells (cell_x, cell_y, event_count, updated_at)
                        VALUES (:cx, :cy, :cnt, :now)
                        ON DUPLICATE KEY UPDATE
                            event_count = event_count + VALUES(event_count),
                            updated_at = VALUES(updated_at)
                    """),
                    {"cx": cx, "cy": cy, "cnt": row.cnt, "now": now},
                )

        db.commit()
        logger.info("aggregated %d heatmap cells", len(rows))
        return len(rows)
    except Exception:
        logger.exception("heatcell aggregation failed")
        db.rollback()
        return 0
    finally:
        db.close()


def _cleanup_old_events():
    """
    删除 90 天前的 movement_events 和 social_events。
    分批删除避免长时间锁表。
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=TTL_DAYS)
        batch = 5000
        total = 0

        # 批量删除 movement_events（使用带参数绑定的 text() 表达式）
        while True:
            ids = (
                db.query(MovementEvent.id)
                .filter(MovementEvent.created_at < cutoff)
                .limit(batch)
                .all()
            )
            if not ids:
                break
            id_list = [r.id for r in ids]
            res = db.query(MovementEvent).filter(MovementEvent.id.in_(id_list)).delete(
                synchronize_session=False
            )
            db.commit()
            total += res
            if res < batch:
                break

        # 批量删除 social_events（使用 ORM filter 带参数绑定）
        from app.models import SocialEvent  # noqa: F401
        while True:
            res = db.query(SocialEvent).filter(
                SocialEvent.created_at < cutoff
            ).delete(synchronize_session=False)
            db.commit()
            total += res
            if res < batch:
                break

        logger.info("cleanup deleted %d old events before %s", total, cutoff.date())
        return total
    except Exception:
        logger.exception("event cleanup failed")
        db.rollback()
        return 0
    finally:
        db.close()


# ─── Scheduler 启动 / 关闭 ──────────────────────────────────────────────


def start():
    """注册定时任务并启动调度器（app startup 时调用）"""
    scheduler.add_job(
        _agg_cells, "interval", minutes=5,
        id="agg_heatmap_cells", replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _cleanup_old_events, "cron", hour=3, minute=0,
        id="cleanup_old_events", replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("world scheduler started: agg=5min, cleanup=daily@03:00 UTC")


def stop():
    scheduler.shutdown(wait=False)
    logger.info("world scheduler stopped")
