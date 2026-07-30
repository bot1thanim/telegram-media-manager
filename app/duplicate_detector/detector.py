"""Duplicate detection with conservative matching and idempotent grouping."""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.logger import AuditAction, log_action
from app.database.models.duplicate_group import (
    DuplicateGroup,
    DuplicateGroupStatus,
    duplicate_group_members,
)
from app.database.models.media import Media, MediaStatus

logger = logging.getLogger(__name__)


async def scan_for_duplicates(session: AsyncSession, media: Media) -> list[Media]:
    """Return conservative metadata matches for one non-deleted media item.

    Telegram's ``file_unique_id`` is already protected by a database unique
    constraint. This detector is deliberately limited to same-type items with
    a known identical size and, for video, an identical known duration. It
    never treats missing metadata as equal, preventing broad false positives.
    """
    if media.status == MediaStatus.DELETED.value or media.file_size_bytes is None:
        return []

    conditions = [
        Media.id != media.id,
        Media.status != MediaStatus.DELETED.value,
        Media.media_type == media.media_type,
        Media.file_size_bytes == media.file_size_bytes,
    ]
    if media.media_type == "video" and media.duration_seconds is not None:
        conditions.append(Media.duration_seconds == media.duration_seconds)

    result = await session.execute(select(Media).where(and_(*conditions)))
    return list(result.scalars().all())


def _group_lock_key(media_ids: list[int]) -> int:
    """Produce a stable signed 64-bit advisory-lock key for a member set."""
    raw = ",".join(str(media_id) for media_id in media_ids).encode()
    return int.from_bytes(
        hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True
    )


async def _lock_group_creation(session: AsyncSession, media_ids: list[int]) -> None:
    """Serialize equivalent group creation on PostgreSQL; tests remain portable."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _group_lock_key(media_ids)},
        )


async def create_duplicate_group(
    session: AsyncSession, media_items: list[Media]
) -> DuplicateGroup | None:
    """Create one pending review group or return its pre-existing equivalent.

    A caller may scan the same item more than once because Telegram retries
    webhooks. The stable advisory lock plus existing-member query keeps this
    operation idempotent across concurrent worker processes.
    """
    item_by_id = {item.id: item for item in media_items if item.id is not None}
    media_ids = sorted(item_by_id)
    if len(media_ids) < 2:
        return None

    await _lock_group_creation(session, media_ids)
    existing_result = await session.execute(
        select(DuplicateGroup)
        .join(
            duplicate_group_members,
            duplicate_group_members.c.group_id == DuplicateGroup.id,
        )
        .where(
            DuplicateGroup.status == DuplicateGroupStatus.PENDING_REVIEW.value,
            duplicate_group_members.c.media_id.in_(media_ids),
        )
    )
    existing_groups = list(existing_result.scalars().unique())
    for group in existing_groups:
        member_result = await session.execute(
            select(duplicate_group_members.c.media_id).where(
                duplicate_group_members.c.group_id == group.id
            )
        )
        if set(member_result.scalars()) == set(media_ids):
            return group

    group = DuplicateGroup(
        status=DuplicateGroupStatus.PENDING_REVIEW.value,
        match_reason="same media type and matching available file metadata",
    )
    session.add(group)
    await session.flush()
    await session.execute(
        duplicate_group_members.insert(),
        [{"group_id": group.id, "media_id": media_id} for media_id in media_ids],
    )
    await log_action(
        session,
        AuditAction.DUPLICATE_GROUP_CREATED,
        details={"item_count": len(media_ids), "media_ids": media_ids},
    )
    return group
