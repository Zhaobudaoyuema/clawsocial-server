"""APScheduler: two-phase deid job cleanup (files @8h, mapping @90d)."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.deid.service import archive_expired_job_files, purge_expired_mapping_jobs

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def _cleanup_expired_jobs():
    db = SessionLocal()
    try:
        archived = archive_expired_job_files(db)
        purged = purge_expired_mapping_jobs(db)
        if archived or purged:
            logger.info(
                "deid_cleanup: archived_files=%d purged_mappings=%d",
                archived,
                purged,
            )
    except Exception:
        logger.exception("deid_cleanup failed")
        db.rollback()
    finally:
        db.close()


def start():
    if not scheduler.running:
        scheduler.add_job(_cleanup_expired_jobs, "interval", hours=1, id="deid_cleanup")
        scheduler.start()
        logger.info("deid_cleanup scheduler started")


def stop():
    if scheduler.running:
        scheduler.shutdown(wait=False)
