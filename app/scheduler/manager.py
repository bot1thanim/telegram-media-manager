"""Persistent APScheduler integration for scheduled publishing jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from telegram.ext import Application

from app.audit.logger import AuditAction, log_action
from app.config import config
from app.database.engine import get_session
from app.database.models.publish_job import PublishJob, PublishJobStatus

if TYPE_CHECKING:
    from app.publishing.worker import PublishWorker

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_worker: PublishWorker | None = None


def _to_sync_database_url(database_url: str) -> str:
    """Convert the async SQLAlchemy URL to the synchronous APScheduler URL."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("sqlite+aiosqlite://"):
        return database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return database_url


def init_scheduler(application: Application, worker: PublishWorker) -> AsyncIOScheduler:
    """Start the persistent scheduler once and register restart recovery."""
    global _scheduler, _worker

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    _worker = worker
    jobstore_url = _to_sync_database_url(config.DATABASE_URL)
    _scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=jobstore_url)},
        timezone=timezone.utc,
    )
    _scheduler.start()
    _scheduler.add_job(
        recover_publish_jobs,
        trigger=DateTrigger(run_date=datetime.now(timezone.utc)),
        id="recover_publish_jobs",
        replace_existing=True,
        misfire_grace_time=60,
    )
    application.bot_data["scheduler"] = _scheduler
    logger.info("APScheduler started with persistent PostgreSQL job store")
    return _scheduler


def get_scheduler() -> AsyncIOScheduler:
    """Return the initialized scheduler or fail loudly during incorrect startup."""
    if _scheduler is None:
        raise RuntimeError("Scheduler has not been initialized.")
    return _scheduler


async def schedule_publish_job(
    job_id: int,
    *,
    run_at: datetime | None = None,
    interval_hours: int | None = None,
) -> str:
    """Persist a one-off or recurring execution for an already-built publish job.

    Exactly one trigger mode is allowed.  The scheduler uses a module-level
    coroutine function, which keeps jobs serializable by APScheduler's SQL
    job store and therefore recoverable after a Render restart.
    """
    if (run_at is None) == (interval_hours is None):
        raise ValueError("Choose exactly one of run_at or interval_hours.")
    if interval_hours is not None and interval_hours <= 0:
        raise ValueError("interval_hours must be a positive integer.")

    scheduler = get_scheduler()
    scheduler_job_id = f"publish_job_{job_id}"
    if run_at is not None:
        if run_at.tzinfo is None:
            raise ValueError("run_at must include a timezone.")
        if run_at <= datetime.now(timezone.utc):
            raise ValueError("run_at must be in the future.")
        trigger = DateTrigger(run_date=run_at)
    else:
        trigger = IntervalTrigger(hours=interval_hours, timezone=timezone.utc)

    scheduler.add_job(
        run_scheduled_publish,
        trigger=trigger,
        args=[job_id],
        id=scheduler_job_id,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    return scheduler_job_id


async def run_scheduled_publish(job_id: int) -> None:
    """Claim a scheduled job and hand its pending queue items to the worker."""
    if _worker is None:
        logger.error(
            "Scheduled publish %d cannot start because the worker is unavailable",
            job_id,
        )
        return

    async with get_session() as session:
        job = await session.get(PublishJob, job_id, with_for_update=True)
        if job is None:
            logger.warning("Scheduled publish %d no longer exists", job_id)
            return
        if job.status in {
            PublishJobStatus.COMPLETED.value,
            PublishJobStatus.STOPPED.value,
        }:
            logger.info(
                "Scheduled publish %d is already terminal (%s)", job_id, job.status
            )
            return
        if job.status == PublishJobStatus.RUNNING.value:
            logger.info("Scheduled publish %d is already running", job_id)
            return

        job.status = PublishJobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        await log_action(
            session,
            AuditAction.PUBLISH_JOB_STARTED,
            actor_telegram_id=job.created_by_user_id,
            details={"scheduled": True},
        )

    await _worker.start_job(job_id)


async def recover_publish_jobs() -> None:
    """Resume incomplete queued/running jobs after a process restart."""
    if _worker is None:
        return

    async with get_session() as session:
        result = await session.execute(
            select(PublishJob.id).where(
                PublishJob.status.in_(
                    [PublishJobStatus.QUEUED.value, PublishJobStatus.RUNNING.value]
                )
            )
        )
        job_ids = list(result.scalars())

    for job_id in job_ids:
        try:
            await run_scheduled_publish(job_id)
        except Exception:
            logger.exception("Failed to recover publish job %d", job_id)


async def shutdown_scheduler() -> None:
    """Stop scheduler dispatch without blocking Render's graceful shutdown."""
    global _scheduler, _worker
    if _scheduler is not None:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)
        _scheduler = None
    _worker = None
