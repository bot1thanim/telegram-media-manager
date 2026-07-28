"""
app/scheduler/manager.py
==========================
APScheduler management.
SRS §16, §16.1: Job Store, persistent scheduling.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from telegram.ext import Application

from app.config import config

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def init_scheduler(application: Application):
    """Initialise the scheduler with SQLAlchemy job store."""
    global _scheduler
    
    # Use the same DATABASE_URL but ensure it's the sync version for APScheduler's SQLAlchemyJobStore
    # APScheduler doesn't natively support asyncpg for JobStore yet without extra wrapping.
    # We use a sync driver for the job store specifically.
    sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    
    jobstores = {
        'default': SQLAlchemyJobStore(url=sync_db_url)
    }
    
    _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone='UTC')
    _scheduler.start()
    logger.info("Scheduler started with persistent JobStore.")


def get_scheduler() -> AsyncIOScheduler:
    if _scheduler is None:
        raise RuntimeError("Scheduler not initialised.")
    return _scheduler


async def schedule_publish_job(
    category_id: int | None,
    order_mode: str,
    run_at: str | None = None, # ISO format or None for now
    interval_hours: int | None = None
):
    """
    SRS §16.2: Schedule a new publish job.
    Implementation will be completed in Phase 5.
    """
    pass
