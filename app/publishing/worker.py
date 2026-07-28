"""
app/publishing/worker.py
==========================
The Publish Worker.
SRS §14, §15
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from telegram.ext import Application
from telegram.error import FloodWait, TelegramError

from app.database.engine import get_session
from app.database.models.publish_job import PublishJob, PublishJobStatus, PublishQueueItem, PublishQueueItemState
from app.database.models.media import Media, MediaStatus
from app.database.models.category import Category
from app.database.models.setting import SettingKey, SETTING_DEFAULTS
from app.audit.logger import log_action, AuditAction
from app.config import config

logger = logging.getLogger(__name__)


async def get_setting_value(session: AsyncSession, key: str) -> Any:
    from app.database.models.setting import Setting
    result = await session.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else SETTING_DEFAULTS.get(key)


class PublishWorker:
    def __init__(self, application: Application):
        self.application = application
        self._running_jobs: dict[int, asyncio.Task] = {}

    async def start_job(self, job_id: int):
        if job_id in self._running_jobs:
            return
        task = asyncio.create_task(self._run_job_loop(job_id))
        self._running_jobs[job_id] = task
        
    async def stop_job(self, job_id: int):
        if job_id in self._running_jobs:
            self._running_jobs[job_id].cancel()
            del self._running_jobs[job_id]

    async def _run_job_loop(self, job_id: int):
        try:
            while True:
                async with get_session() as session:
                    job = await session.get(PublishJob, job_id)
                    if not job or job.status != PublishJobStatus.RUNNING.value:
                        break
                        
                    result = await session.execute(
                        select(PublishQueueItem)
                        .where(PublishQueueItem.job_id == job_id)
                        .where(PublishQueueItem.state == PublishQueueItemState.PENDING.value)
                        .order_by(PublishQueueItem.position.asc())
                        .limit(1)
                    )
                    queue_item = result.scalar_one_or_none()
                    
                    if not queue_item:
                        job.status = PublishJobStatus.COMPLETED.value
                        job.completed_at = datetime.now(timezone.utc)
                        await log_action(session, AuditAction.PUBLISH_JOB_COMPLETED, target_media_id=job_id)
                        break
                        
                    media = await session.get(Media, queue_item.media_id)
                    category = await session.get(Category, media.category_id)
                    target_thread_id = category.telegram_thread_id if category else config.GENERAL_TOPIC_THREAD_ID
                    
                    try:
                        await self._send_media(media, config.GROUP_CHAT_ID, target_thread_id)
                        
                        queue_item.state = PublishQueueItemState.SENT.value
                        queue_item.sent_at = datetime.now(timezone.utc)
                        job.processed_count += 1
                        
                        # Update media status to PUBLISHED
                        media.status = MediaStatus.PUBLISHED.value
                        media.published_at = datetime.now(timezone.utc)
                        
                        await log_action(session, AuditAction.PUBLISH_ITEM_SENT, target_media_id=media.id)
                        
                    except FloodWait as e:
                        logger.warning("FloodWait: sleeping for %d seconds", e.retry_after)
                        await asyncio.sleep(e.retry_after)
                        continue
                        
                    except TelegramError as e:
                        logger.error("Telegram error sending media %d: %s", media.id, e)
                        queue_item.state = PublishQueueItemState.FAILED.value
                        queue_item.error_message = str(e)
                        job.failed_count += 1
                        
                        if "file is too big" in str(e).lower() or "wrong file identifier" in str(e).lower():
                            media.status = MediaStatus.BROKEN.value
                            
                        await log_action(session, AuditAction.PUBLISH_ITEM_FAILED, target_media_id=media.id, details={"error": str(e)})
                    
                    delay = await get_setting_value(session, SettingKey.FLOOD_CONTROL_DELAY)
                    await asyncio.sleep(float(delay))
                    
        except asyncio.CancelledError:
            pass
        finally:
            if job_id in self._running_jobs:
                del self._running_jobs[job_id]

    async def _send_media(self, media: Media, chat_id: int, thread_id: int):
        bot = self.application.bot
        common_kwargs = {
            "chat_id": chat_id,
            "message_thread_id": thread_id,
            "caption": media.caption,
        }
        
        if media.media_type == "video":
            await bot.send_video(video=media.file_id, **common_kwargs)
        elif media.media_type == "photo":
            await bot.send_photo(photo=media.file_id, **common_kwargs)
        elif media.media_type == "document":
            await bot.send_document(document=media.file_id, **common_kwargs)
        elif media.media_type == "animation":
            await bot.send_animation(animation=media.file_id, **common_kwargs)
        else:
            raise ValueError(f"Unsupported media type: {media.media_type}")
