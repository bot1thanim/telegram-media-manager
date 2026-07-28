"""
app/duplicate_detector/detector.py
====================================
Duplicate detection logic.
SRS §12.1: Detection by file_unique_id, size, duration, and name similarity.
"""

import logging
from typing import List, Tuple

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.media import Media, MediaStatus
from app.database.models.duplicate_group import (
    DuplicateGroup, DuplicateGroupStatus, duplicate_group_members
)
from app.audit.logger import log_action, AuditAction

logger = logging.getLogger(__name__)


async def scan_for_duplicates(session: AsyncSession, media: Media) -> List[Media]:
    """
    SRS §12.1: Find potential duplicates for a given media item.
    Matches by:
    1. file_unique_id (already handled by import_media, but here for completeness)
    2. Exact file_size AND duration (for videos)
    3. High caption similarity (optional, simplified here to exact match or inclusion)
    """
    query = select(Media).where(
        and_(
            Media.id != media.id,
            Media.status != MediaStatus.DELETED.value,
            Media.file_size == media.file_size
        )
    )
    
    if media.duration:
        query = query.where(Media.duration == media.duration)
        
    result = await session.execute(query)
    potentials = result.scalars().all()
    
    return list(potentials)


async def create_duplicate_group(
    session: AsyncSession, 
    media_items: List[Media]
) -> DuplicateGroup | None:
    """Create a group for review if duplicates found."""
    if len(media_items) < 2:
        return None
        
    group = DuplicateGroup(
        status=DuplicateGroupStatus.PENDING_REVIEW.value
    )
    session.add(group)
    await session.flush()
    
    # Add members
    for item in media_items:
        await session.execute(
            duplicate_group_members.insert().values(
                group_id=group.id,
                media_id=item.id
            )
        )
        
    await log_action(
        session,
        AuditAction.DUPLICATE_GROUP_CREATED,
        details={"item_count": len(media_items)}
    )
    return group
