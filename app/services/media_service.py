"""
app/services/media_service.py
================================
Business logic for media management and importing.
SRS §9, §10, §12, §13
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.logger import AuditAction, log_action
from app.database.models.media import Media, MediaStatus

logger = logging.getLogger(__name__)


async def import_media(
    session: AsyncSession,
    file_id: str,
    file_unique_id: str,
    media_type: str,
    file_size: int,
    caption: str | None = None,
    duration: int | None = None,
    width: int | None = None,
    height: int | None = None,
    uploader_id: int | None = None,
    uploader_name: str | None = None,
    message_id: int | None = None,
    chat_id: int | None = None,
) -> tuple[Media, bool]:
    """SRS §9: Import media from Telegram."""
    result = await session.execute(
        select(Media).where(Media.file_unique_id == file_unique_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.file_id = file_id
        await session.flush()
        return existing, False

    media = Media(
        file_id=file_id,
        file_unique_id=file_unique_id,
        media_type=media_type,
        file_size_bytes=file_size,
        caption=caption,
        duration_seconds=duration,
        uploaded_by_user_id=uploader_id,
        source_message_id=message_id,
        status=MediaStatus.WAITING_CATEGORIZATION.value,
    )
    session.add(media)
    await session.flush()

    await log_action(
        session,
        AuditAction.MEDIA_IMPORTED,
        actor_telegram_id=uploader_id,
        target_media_id=media.id,
    )
    return media, True


async def get_media_by_id(session: AsyncSession, media_id: int) -> Media | None:
    return await session.get(Media, media_id)


async def categorize_media(
    session: AsyncSession, media_id: int, category_id: int, actor_id: int | None = None
) -> Media:
    """SRS §10.1: Categorize and mark as ready to publish."""
    media = await get_media_by_id(session, media_id)
    if not media:
        raise ValueError("Media not found.")

    media.category_id = category_id
    media.status = MediaStatus.READY_TO_PUBLISH.value

    await session.flush()

    await log_action(
        session,
        AuditAction.MEDIA_CATEGORIZED,
        actor_telegram_id=actor_id,
        target_media_id=media_id,
        target_category_id=category_id,
    )
    return media


async def move_to_recycle_bin(
    session: AsyncSession, media_id: int, actor_id: int | None = None
) -> Media:
    """SRS §13: Soft delete."""
    media = await get_media_by_id(session, media_id)
    if not media:
        raise ValueError("Media not found.")

    media.pre_delete_status = media.status
    media.status = MediaStatus.DELETED.value
    media.deleted_at = datetime.now(timezone.utc)

    await session.flush()
    await log_action(
        session,
        AuditAction.MEDIA_DELETED,
        actor_telegram_id=actor_id,
        target_media_id=media_id,
    )
    return media


async def restore_from_recycle_bin(
    session: AsyncSession, media_id: int, actor_id: int | None = None
) -> Media:
    """SRS §13: Restore from soft delete."""
    media = await get_media_by_id(session, media_id)
    if not media:
        raise ValueError("Media not found.")

    media.status = media.pre_delete_status or MediaStatus.WAITING_CATEGORIZATION.value
    media.deleted_at = None
    media.pre_delete_status = None

    await session.flush()
    await log_action(
        session,
        AuditAction.MEDIA_RESTORED,
        actor_telegram_id=actor_id,
        target_media_id=media_id,
    )
    return media


async def permanently_delete_media(
    session: AsyncSession, media_id: int, actor_id: int | None = None
) -> None:
    media = await get_media_by_id(session, media_id)
    if not media:
        raise ValueError("Media not found.")

    await session.delete(media)
    await session.flush()
    await log_action(
        session,
        AuditAction.MEDIA_PERMANENTLY_DELETED,
        actor_telegram_id=actor_id,
        target_media_id=media_id,
    )


async def get_next_media_for_sorting(
    session: AsyncSession, exclude_ids: list[int] | None = None
) -> Media | None:
    query = select(Media).where(
        Media.status == MediaStatus.WAITING_CATEGORIZATION.value
    )
    if exclude_ids:
        query = query.where(Media.id.not_in(exclude_ids))

    query = query.order_by(Media.created_at.asc()).limit(1)
    result = await session.execute(query)
    return result.scalar_one_or_none()
