"""APScheduler: delete deid job files 8h after completion."""
import logging
import shutil
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.deid.storage import DEID_ROOT, JOB_RETENTION_HOURS
from app.models_deid import DeidEntityMapping, DeidJob, DeidJobEntity, DeidJobEntityAlias
from app.time_utils import now_beijing

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def _cleanup_expired_jobs():
    db = SessionLocal()
    try:
        cutoff = now_beijing() - timedelta(hours=JOB_RETENTION_HOURS)
        jobs = (
            db.query(DeidJob)
            .filter(DeidJob.status == "done", DeidJob.completed_at < cutoff)
            .all()
        )
        for job in jobs:
            job_id = job.id
            db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).delete()
            alias_subq = db.query(DeidJobEntity.id).filter(DeidJobEntity.job_id == job_id)
            db.query(DeidJobEntityAlias).filter(
                DeidJobEntityAlias.job_entity_id.in_(alias_subq)
            ).delete(synchronize_session=False)
            db.query(DeidJobEntity).filter(DeidJobEntity.job_id == job_id).delete()
            db.delete(job)
            d = DEID_ROOT / str(job_id)
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        if jobs:
            db.commit()
            logger.info("deid_cleanup: removed %d expired jobs", len(jobs))
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
