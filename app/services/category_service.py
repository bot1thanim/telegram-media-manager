"""
app/services/category_service.py
===================================
Business logic for category management.
SRS §11
"""

import logging
from typing import Sequence

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.category import Category
from app.database.models.media import Media, MediaStatus
from app.audit.logger import log_action, AuditAction

logger = logging.getLogger(__name__)


async def create_category(
    session: AsyncSession,
    name: str,
    emoji: str | None = None,
    actor_id: int | None = None
) -> Category:
    result = await session.execute(select(Category).where(Category.name == name))
    if result.scalar_one_or_none():
        raise ValueError(f"Category '{name}' already exists.")

    category = Category(name=name, emoji=emoji)
    session.add(category)
    await session.flush()

    await log_action(
        session,
        AuditAction.CATEGORY_CREATED,
        actor_telegram_id=actor_id,
        target_category_id=category.id
    )
    return category


async def get_all_categories(session: AsyncSession) -> Sequence[Category]:
    result = await session.execute(select(Category).order_by(Category.name))
    return result.scalars().all()


async def get_category_by_id(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


async def delete_category(
    session: AsyncSession,
    category_id: int,
    actor_id: int | None = None
) -> int:
    category = await get_category_by_id(session, category_id)
    if not category:
        raise ValueError("Category not found.")

    # Return items to sorting queue (WAITING_CATEGORIZATION)
    result = await session.execute(
        update(Media)
        .where(Media.category_id == category_id)
        .values(category_id=None, status=MediaStatus.WAITING_CATEGORIZATION.value)
    )
    affected_items = result.rowcount

    await session.delete(category)
    await session.flush()

    await log_action(
        session,
        AuditAction.CATEGORY_DELETED,
        actor_telegram_id=actor_id,
        target_category_id=category_id
    )
    return affected_items
