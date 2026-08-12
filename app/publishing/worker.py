"""Transactional, at-most-once publish worker for Telegram media."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from telegram.error import RetryAfter, TelegramError
from telegram.ext import Application

from app.audit.logger import AuditAction, log_action
from app.config import config
from app.database.engine import get_session
from app.database.models.category import Category
from app.database.models.media import Media, MediaStatus
from app.database.models.publish_job import (
    PublishJob,
    PublishJobStatus,
    PublishQueueItem,
    PublishQueueItemState,
)
from app.database.models.setting import SETTING_DEFAULTS, Setting, SettingKey

logger = logging.getLogger(__name__)


async def get_setting_value(session, key: str) -> Any:
    """Read a configurable setting and fall back to the documented default."""
    result = await session.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting is not None else SETTING_DEFAULTS.get(key)


class PublishWorker:
    """Runs one in-process task per publish job with durable item state transitions."""

    def __init__(self, application: Application):
        self.application = application
        self._running_jobs: dict[int, asyncio.Task[None]] = {}

    async def start_job(self, job_id: int) -> None:
        """Start a worker only if the job does not already have a live task."""
        task = self._running_jobs.get(job_id)
        if task is not None and not task.done():
            return
        self._running_jobs[job_id] = asyncio.create_task(
            self._run_job_loop(job_id), name=f"publish-job-{job_id}"
        )

    async def stop_job(self, job_id: int) -> None:
        """Cancel and await a running task so it cannot leak beyond shutdown."""
        task = self._running_jobs.get(job_id)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            if self._running_jobs.get(job_id) is task:
                self._running_jobs.pop(job_id, None)

    async def shutdown(self) -> None:
        """Stop every worker task before closing the Telegram application."""
        await asyncio.gather(
            *(self.stop_job(job_id) for job_id in list(self._running_jobs)),
            return_exceptions=True,
        )

    async def _run_job_loop(self, job_id: int) -> None:
        try:
            await self._mark_stale_claims_failed(job_id)
            while True:
                claimed = await self._claim_next_item(job_id)
                if claimed is None:
                    return

                queue_item_id, media_id, media_type, file_id, caption, thread_id = (
                    claimed
                )
                try:
                    message = await self._send_media(
                        media_type=media_type,
                        file_id=file_id,
                        caption=caption,
                        chat_id=config.TARGET_GROUP_CHAT_ID,
                        thread_id=thread_id,
                    )
                except RetryAfter as exc:
                    logger.warning(
                        "FloodWait while publishing job %d; retrying in %d seconds",
                        job_id,
                        exc.retry_after,
                    )
                    await self._return_item_to_pending(queue_item_id)
                    await asyncio.sleep(exc.retry_after)
                    continue
                except TelegramError as exc:
                    await self._mark_item_failed(queue_item_id, media_id, str(exc))
                except Exception as exc:
                    logger.exception(
                        "Unexpected publish failure for job %d item %d",
                        job_id,
                        queue_item_id,
                    )
                    await self._mark_item_failed(queue_item_id, media_id, str(exc))
                else:
                    await self._mark_item_sent(
                        queue_item_id, media_id, getattr(message, "message_id", None)
                    )

                delay = await self._get_publish_delay()
                if delay:
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info("Publish job %d cancelled", job_id)
            raise
        finally:
            current_task = asyncio.current_task()
            if self._running_jobs.get(job_id) is current_task:
                self._running_jobs.pop(job_id, None)

    async def _claim_next_item(
        self, job_id: int
    ) -> tuple[int, int, str, str, str | None, int | None] | None:
        """Commit a durable SENDING claim before any external Telegram call.

        A process restart with an uncertain in-flight Telegram result is handled
        as failed rather than retried automatically.  That trades a manual
        retry for the stronger guarantee that the bot never posts the same item
        twice merely because a worker crashed after Telegram accepted it.
        """
        async with get_session() as session:
            job = await session.get(PublishJob, job_id, with_for_update=True)
            if job is None or job.status != PublishJobStatus.RUNNING.value:
                return None

            while True:
                result = await session.execute(
                    select(PublishQueueItem)
                    .where(
                        PublishQueueItem.job_id == job_id,
                        PublishQueueItem.state == PublishQueueItemState.PENDING.value,
                    )
                    .order_by(PublishQueueItem.position.asc())
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                queue_item = result.scalar_one_or_none()
                if queue_item is None:
                    job.status = PublishJobStatus.COMPLETED.value
                    job.completed_at = datetime.now(timezone.utc)
                    await log_action(
                        session,
                        AuditAction.PUBLISH_JOB_COMPLETED,
                        actor_telegram_id=job.created_by_user_id,
                        details={"job_id": job_id},
                    )
                    return None

                media = await session.get(
                    Media, queue_item.media_id, with_for_update=True
                )
                if media is None or media.status != MediaStatus.READY_TO_PUBLISH.value:
                    queue_item.state = PublishQueueItemState.SKIPPED.value
                    queue_item.last_error = (
                        "Media is unavailable or is not ready to publish."
                    )
                    continue

                category = (
                    await session.get(Category, media.category_id)
                    if media.category_id
                    else None
                )
                thread_id = (
                    category.telegram_thread_id
                    if category
                    else config.GENERAL_TOPIC_THREAD_ID
                )
                queue_item.state = PublishQueueItemState.SENDING.value
                queue_item.last_error = None
                return (
                    queue_item.id,
                    media.id,
                    media.media_type,
                    media.file_id,
                    media.caption,
                    thread_id,
                )

    async def _mark_stale_claims_failed(self, job_id: int) -> None:
        """Resolve interrupted claims conservatively to preserve at-most-once sends."""
        async with get_session() as session:
            result = await session.execute(
                select(PublishQueueItem)
                .where(
                    PublishQueueItem.job_id == job_id,
                    PublishQueueItem.state == PublishQueueItemState.SENDING.value,
                )
                .with_for_update()
            )
            for queue_item in result.scalars():
                queue_item.state = PublishQueueItemState.FAILED.value
                queue_item.last_error = (
                    "Publish process restarted while Telegram delivery outcome was unknown; "
                    "not retried automatically to avoid a duplicate post."
                )

    async def _return_item_to_pending(self, queue_item_id: int) -> None:
        async with get_session() as session:
            item = await session.get(
                PublishQueueItem, queue_item_id, with_for_update=True
            )
            if item is not None and item.state == PublishQueueItemState.SENDING.value:
                item.state = PublishQueueItemState.PENDING.value

    async def _mark_item_sent(
        self, queue_item_id: int, media_id: int, message_id: int | None
    ) -> None:
        async with get_session() as session:
            item = await session.get(
                PublishQueueItem, queue_item_id, with_for_update=True
            )
            media = await session.get(Media, media_id, with_for_update=True)
            if (
                item is None
                or media is None
                or item.state != PublishQueueItemState.SENDING.value
            ):
                return
            item.state = PublishQueueItemState.SENT.value
            item.sent_at = datetime.now(timezone.utc)
            media.status = MediaStatus.PUBLISHED.value
            media.published_at = datetime.now(timezone.utc)
            media.published_message_id = message_id
            await log_action(
                session, AuditAction.PUBLISH_ITEM_SENT, target_media_id=media_id
            )

    async def _mark_item_failed(
        self, queue_item_id: int, media_id: int, error: str
    ) -> None:
        safe_error = error[:2000]
        async with get_session() as session:
            item = await session.get(
                PublishQueueItem, queue_item_id, with_for_update=True
            )
            media = await session.get(Media, media_id, with_for_update=True)
            if item is None or item.state != PublishQueueItemState.SENDING.value:
                return
            item.state = PublishQueueItemState.FAILED.value
            item.last_error = safe_error
            if media is not None and any(
                marker in error.lower()
                for marker in (
                    "file is too big",
                    "wrong file identifier",
                    "file reference",
                    "file_id",
                )
            ):
                media.status = MediaStatus.BROKEN.value
            await log_action(
                session,
                AuditAction.PUBLISH_ITEM_FAILED,
                target_media_id=media_id,
                details={"error": safe_error},
            )

    async def _get_publish_delay(self) -> float:
        async with get_session() as session:
            value = await get_setting_value(
                session, SettingKey.FLOOD_CONTROL_DELAY_SECONDS
            )
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            logger.warning("Invalid flood-control delay %r; using default", value)
            return float(SETTING_DEFAULTS[SettingKey.FLOOD_CONTROL_DELAY_SECONDS])

    async def _send_media(
        self,
        *,
        media_type: str,
        file_id: str,
        caption: str | None,
        chat_id: int,
        thread_id: int | None,
    ):
        """Send one supported Telegram media type and return its Message."""
        common_kwargs: dict[str, Any] = {"chat_id": chat_id, "caption": caption}
        if thread_id is not None:
            common_kwargs["message_thread_id"] = thread_id

        if media_type == "video":
            return await self.application.bot.send_video(video=file_id, **common_kwargs)
        if media_type == "photo":
            return await self.application.bot.send_photo(photo=file_id, **common_kwargs)
        if media_type == "document":
            return await self.application.bot.send_document(
                document=file_id, **common_kwargs
            )
        raise ValueError(f"Unsupported media type: {media_type}")
