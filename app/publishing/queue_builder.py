"""
app/publishing/queue_builder.py
=================================
Builds the publish queue based on selected order.
SRS §14.2
"""

import random
import logging
from typing import List, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.media import Media, MediaStatus
from app.database.models.publish_job import PublishQueueItem, PublishQueueItemState

logger = logging.getLogger(__name__)


class OrderMode:
    RANDOM = "random"
    OLDEST_FIRST = "oldest_first"
    NEWEST_FIRST = "newest_first"
    SHORTEST_FIRST = "shortest_first"
    LONGEST_FIRST = "longest_first"


async def build_queue(
    session: AsyncSession,
    job_id: int,
    category_id: int | None = None,
    order_mode: str = OrderMode.OLDEST_FIRST,
    limit: int | None = None
) -> int:
    # Only READY_TO_PUBLISH items
    query = select(Media).where(Media.status == MediaStatus.READY_TO_PUBLISH.value)
    
    if category_id:
        query = query.where(Media.category_id == category_id)
        
    if order_mode == OrderMode.OLDEST_FIRST:
        query = query.order_by(Media.created_at.asc())
    elif order_mode == OrderMode.NEWEST_FIRST:
        query = query.order_by(Media.created_at.desc())
    elif order_mode == OrderMode.SHORTEST_FIRST:
        query = query.order_by(Media.duration_seconds.asc().nullslast())
    elif order_mode == OrderMode.LONGEST_FIRST:
        query = query.order_by(Media.duration_seconds.desc().nullslast())
        
    result = await session.execute(query)
    items = list(result.scalars().all())
    
    if order_mode == OrderMode.RANDOM:
        random.shuffle(items)
        
    if limit:
        items = items[:limit]
        
    for idx, media in enumerate(items):
        queue_item = PublishQueueItem(
            job_id=job_id,
            media_id=media.id,
            position=idx,
            state=PublishQueueItemState.PENDING.value
        )
        session.add(queue_item)
        
    await session.flush()
    return len(items)
