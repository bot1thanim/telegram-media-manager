"""Transactional services shared by live and historical topic synchronization."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.logger import AuditAction, log_action
from app.database.models.category import Category
from app.database.models.media import Media, MediaStatus
from app.database.models.topic_catalog import TopicCatalog
from app.sync.matching import normalize_topic_name


@dataclass(frozen=True, slots=True)
class MediaIngestResult:
    """Outcome of one source message ingestion attempt."""

    media: Media
    is_new: bool
    duplicate_reason: str | None = None


async def upsert_topic(
    session: AsyncSession,
    *,
    chat_id: int,
    thread_id: int,
    name: str,
    icon_color: int | None = None,
    is_closed: bool = False,
    is_deleted: bool = False,
) -> TopicCatalog:
    """Create or refresh a forum-topic catalog entry within the active transaction."""
    normalized_name = normalize_topic_name(name)
    if not normalized_name:
        raise ValueError("Forum topic name cannot be empty.")

    result = await session.execute(
        select(TopicCatalog)
        .where(TopicCatalog.chat_id == chat_id, TopicCatalog.thread_id == thread_id)
        .with_for_update()
    )
    topic = result.scalar_one_or_none()
    if topic is None:
        topic = TopicCatalog(
            chat_id=chat_id,
            thread_id=thread_id,
            name=name.strip(),
            normalized_name=normalized_name,
            icon_color=icon_color,
            is_closed=is_closed,
            is_deleted=is_deleted,
        )
        session.add(topic)
    else:
        topic.name = name.strip()
        topic.normalized_name = normalized_name
        topic.icon_color = icon_color
        topic.is_closed = is_closed
        topic.is_deleted = is_deleted
    await session.flush()
    return topic


async def list_active_topics(session: AsyncSession, chat_id: int) -> list[TopicCatalog]:
    """Return current active topics in a deterministic display order."""
    result = await session.execute(
        select(TopicCatalog)
        .where(
            TopicCatalog.chat_id == chat_id,
            TopicCatalog.is_deleted.is_(False),
            TopicCatalog.is_closed.is_(False),
        )
        .order_by(TopicCatalog.normalized_name.asc(), TopicCatalog.thread_id.asc())
    )
    return list(result.scalars().all())


async def ensure_source_category(
    session: AsyncSession,
    *,
    source_group_id: int,
    source_thread_id: int,
    topic_name: str,
    actor_id: int | None = None,
) -> tuple[Category, bool]:
    """Return the category bound to a source topic, creating it when absent.

    A manually created category with an equal normalized name can be adopted once
    only when it is not already bound to another source topic. This preserves
    existing user work while preventing a topic from silently hijacking another
    category.
    """
    result = await session.execute(
        select(Category)
        .where(
            Category.source_group_id == source_group_id,
            Category.source_thread_id == source_thread_id,
        )
        .with_for_update()
    )
    category = result.scalar_one_or_none()
    if category is not None:
        return category, False

    normalized_name = normalize_topic_name(topic_name)
    candidates = (
        await session.execute(
            select(Category).where(Category.is_deleted.is_(False)).with_for_update()
        )
    ).scalars()
    for candidate in candidates:
        if normalize_topic_name(candidate.name) != normalized_name:
            continue
        if candidate.source_group_id is None and candidate.source_thread_id is None:
            candidate.source_group_id = source_group_id
            candidate.source_thread_id = source_thread_id
            await session.flush()
            return candidate, False
        raise ValueError(
            "A category with the same normalized name is already bound to another source topic."
        )

    clean_name = " ".join(topic_name.split())
    if not clean_name:
        raise ValueError("Forum topic name cannot be empty.")
    category = Category(
        name=clean_name,
        source_group_id=source_group_id,
        source_thread_id=source_thread_id,
    )
    session.add(category)
    await session.flush()
    await log_action(
        session,
        AuditAction.CATEGORY_CREATED,
        actor_telegram_id=actor_id,
        target_category_id=category.id,
        details={
            "source_group_id": source_group_id,
            "source_thread_id": source_thread_id,
            "created_by": "topic_sync",
        },
    )
    return category, True


async def ingest_source_media(
    session: AsyncSession,
    *,
    file_id: str,
    file_unique_id: str,
    media_type: str,
    file_size: int | None,
    caption: str | None,
    duration: int | None,
    uploader_id: int | None,
    source_group_id: int,
    source_thread_id: int,
    source_message_id: int,
    category_id: int,
    actor_id: int | None = None,
) -> MediaIngestResult:
    """Insert one source media message exactly once and mark it ready to publish."""
    existing_source = (
        await session.execute(
            select(Media)
            .where(
                Media.source_group_id == source_group_id,
                Media.source_message_id == source_message_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing_source is not None:
        return MediaIngestResult(existing_source, False, "source_message")

    existing_file = (
        await session.execute(
            select(Media).where(Media.file_unique_id == file_unique_id).with_for_update()
        )
    ).scalar_one_or_none()
    if existing_file is not None:
        return MediaIngestResult(existing_file, False, "file_unique_id")

    media = Media(
        file_id=file_id,
        file_unique_id=file_unique_id,
        media_type=media_type,
        file_size_bytes=file_size,
        caption=caption,
        duration_seconds=duration,
        uploaded_by_user_id=uploader_id,
        source_message_id=source_message_id,
        source_group_id=source_group_id,
        source_thread_id=source_thread_id,
        category_id=category_id,
        status=MediaStatus.READY_TO_PUBLISH.value,
    )
    session.add(media)
    await session.flush()
    await log_action(
        session,
        AuditAction.MEDIA_IMPORTED_DIRECT_TO_CATEGORY,
        actor_telegram_id=actor_id,
        target_media_id=media.id,
        target_category_id=category_id,
        details={
            "source_group_id": source_group_id,
            "source_thread_id": source_thread_id,
            "source_message_id": source_message_id,
        },
    )
    return MediaIngestResult(media, True)
