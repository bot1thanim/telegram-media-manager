"""Validated JSON backup and restore service for categories and media metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.logger import AuditAction, log_action
from app.database.models.backup import Backup
from app.database.models.category import Category
from app.database.models.media import Media, MediaStatus, MediaType

BACKUP_SCHEMA_VERSION = 1
MAX_BACKUP_CATEGORIES = 10_000
MAX_BACKUP_MEDIA = 100_000


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Invalid timestamp type in backup.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO-8601 timestamp in backup.") from exc
    if parsed.tzinfo is None:
        raise ValueError("Backup timestamps must include a timezone.")
    return parsed


def _validate_backup_payload(json_data: str) -> dict[str, Any]:
    try:
        payload = json.loads(json_data)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Backup file is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise TypeError("Backup root must be a JSON object.")
    if payload.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise ValueError("Unsupported backup schema version.")

    categories = payload.get("categories")
    media_items = payload.get("media")
    if not isinstance(categories, list) or not isinstance(media_items, list):
        raise TypeError("Backup must contain categories and media arrays.")
    if len(categories) > MAX_BACKUP_CATEGORIES or len(media_items) > MAX_BACKUP_MEDIA:
        raise ValueError("Backup exceeds supported record limits.")
    return payload


async def create_backup(
    session: AsyncSession,
    actor_id: int | None = None,
    *,
    trigger_type: str = "manual",
) -> str:
    """Export all recoverable metadata and persist only a schema-valid audit record."""
    if trigger_type not in {"manual", "auto"}:
        raise ValueError("trigger_type must be manual or auto.")

    categories = list((await session.execute(select(Category))).scalars())
    media_items = list((await session.execute(select(Media))).scalars())
    data = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "categories": [
            {
                "backup_id": category.id,
                "name": category.name,
                "emoji": category.emoji,
                "telegram_thread_id": category.telegram_thread_id,
            }
            for category in categories
        ],
        "media": [
            {
                "file_unique_id": media.file_unique_id,
                "file_id": media.file_id,
                "media_type": media.media_type,
                "duration_seconds": media.duration_seconds,
                "file_size_bytes": media.file_size_bytes,
                "caption": media.caption,
                "uploaded_by_user_id": media.uploaded_by_user_id,
                "uploaded_at": media.uploaded_at.isoformat()
                if media.uploaded_at
                else None,
                "source_message_id": media.source_message_id,
                "category_backup_id": media.category_id,
                "status": media.status,
                "published_at": media.published_at.isoformat()
                if media.published_at
                else None,
                "published_message_id": media.published_message_id,
            }
            for media in media_items
        ],
    }
    json_data = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    session.add(
        Backup(
            triggered_by_user_id=actor_id,
            trigger_type=trigger_type,
            schema_version=BACKUP_SCHEMA_VERSION,
            categories_count=len(categories),
            media_count=len(media_items),
        )
    )
    await log_action(
        session,
        AuditAction.BACKUP_CREATED,
        actor_telegram_id=actor_id,
        details={"categories": len(categories), "media": len(media_items)},
    )
    return json_data


async def restore_backup(
    session: AsyncSession, json_data: str, actor_id: int | None = None
) -> tuple[int, int]:
    """Upsert a validated backup without trusting source primary keys or category IDs."""
    data = _validate_backup_payload(json_data)
    category_id_map: dict[int, int] = {}
    categories_restored = 0
    media_restored = 0

    for raw_category in data["categories"]:
        if not isinstance(raw_category, dict):
            raise TypeError("Each category entry must be an object.")
        backup_id = raw_category.get("backup_id")
        name = raw_category.get("name")
        if (
            not isinstance(backup_id, int)
            or not isinstance(name, str)
            or not name.strip()
        ):
            raise ValueError(
                "Each category requires a numeric backup_id and non-empty name."
            )
        name = name.strip()
        if len(name) > 255:
            raise ValueError("Category name is too long.")

        result = await session.execute(select(Category).where(Category.name == name))
        category = result.scalar_one_or_none()
        if category is None:
            category = Category(name=name)
            session.add(category)
            await session.flush()
        emoji = raw_category.get("emoji")
        if emoji is not None and not isinstance(emoji, str):
            raise ValueError("Invalid category emoji.")
        category.emoji = emoji

        thread_id = raw_category.get("telegram_thread_id")
        if thread_id is not None and not isinstance(thread_id, int):
            raise ValueError("Invalid Telegram thread ID.")
        if thread_id is not None:
            conflict = await session.execute(
                select(Category).where(
                    Category.telegram_thread_id == thread_id,
                    Category.id != category.id,
                )
            )
            if conflict.scalar_one_or_none() is not None:
                raise ValueError(
                    "A Telegram topic is already linked to another category."
                )
        category.telegram_thread_id = thread_id
        category_id_map[backup_id] = category.id
        categories_restored += 1

    for raw_media in data["media"]:
        if not isinstance(raw_media, dict):
            raise TypeError("Each media entry must be an object.")
        file_unique_id = raw_media.get("file_unique_id")
        file_id = raw_media.get("file_id")
        media_type = raw_media.get("media_type")
        status = raw_media.get("status")
        if not all(
            isinstance(value, str) and value
            for value in (file_unique_id, file_id, media_type, status)
        ):
            raise ValueError(
                "Each media entry requires file identifiers, type and status."
            )
        if media_type not in {item.value for item in MediaType}:
            raise ValueError("Backup contains an unsupported media type.")
        if status not in {item.value for item in MediaStatus}:
            raise ValueError("Backup contains an unsupported media status.")

        result = await session.execute(
            select(Media).where(Media.file_unique_id == file_unique_id)
        )
        media = result.scalar_one_or_none()
        if media is None:
            media = Media(
                file_unique_id=file_unique_id, file_id=file_id, media_type=media_type
            )
            session.add(media)

        category_backup_id = raw_media.get("category_backup_id")
        if category_backup_id is not None and not isinstance(category_backup_id, int):
            raise ValueError("Invalid media category reference.")
        if category_backup_id is not None and category_backup_id not in category_id_map:
            raise ValueError("Media references a missing backup category.")

        duration = raw_media.get("duration_seconds")
        size = raw_media.get("file_size_bytes")
        uploader = raw_media.get("uploaded_by_user_id")
        source_message_id = raw_media.get("source_message_id")
        published_message_id = raw_media.get("published_message_id")
        for value, label in (
            (duration, "duration_seconds"),
            (size, "file_size_bytes"),
            (uploader, "uploaded_by_user_id"),
            (source_message_id, "source_message_id"),
            (published_message_id, "published_message_id"),
        ):
            if value is not None and not isinstance(value, int):
                raise ValueError(f"Invalid {label} in backup.")

        caption = raw_media.get("caption")
        if caption is not None and not isinstance(caption, str):
            raise ValueError("Invalid media caption.")
        media.file_id = file_id
        media.media_type = media_type
        media.duration_seconds = duration
        media.file_size_bytes = size
        media.caption = caption
        media.uploaded_by_user_id = uploader
        media.uploaded_at = _parse_optional_datetime(
            raw_media.get("uploaded_at")
        ) or datetime.now(timezone.utc)
        media.source_message_id = source_message_id
        media.category_id = category_id_map.get(category_backup_id)
        media.status = status
        media.published_at = _parse_optional_datetime(raw_media.get("published_at"))
        media.published_message_id = published_message_id
        media_restored += 1

    await session.flush()
    await log_action(
        session,
        AuditAction.BACKUP_RESTORED,
        actor_telegram_id=actor_id,
        details={"categories": categories_restored, "media": media_restored},
    )
    return categories_restored, media_restored
