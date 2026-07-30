"""Transactional business logic for category management."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.logger import AuditAction, log_action
from app.database.models.category import Category
from app.database.models.media import Media, MediaStatus

logger = logging.getLogger(__name__)
_MAX_CATEGORY_NAME_LENGTH = 100


def _normalize_name(name: str) -> str:
    normalized = " ".join(name.split())
    if not normalized:
        raise ValueError("שם הקטגוריה אינו יכול להיות ריק.")
    if len(normalized) > _MAX_CATEGORY_NAME_LENGTH:
        raise ValueError(
            f"שם הקטגוריה ארוך מדי (מקסימום {_MAX_CATEGORY_NAME_LENGTH} תווים)."
        )
    return normalized


async def create_category(
    session: AsyncSession,
    name: str,
    emoji: str | None = None,
    actor_id: int | None = None,
) -> Category:
    """Create a normalized, case-insensitively unique category and audit it."""
    normalized_name = _normalize_name(name)
    result = await session.execute(
        select(Category.id).where(func.lower(Category.name) == normalized_name.lower())
    )
    if result.scalar_one_or_none() is not None:
        raise ValueError(f"הקטגוריה '{normalized_name}' כבר קיימת.")

    category = Category(name=normalized_name, emoji=emoji)
    session.add(category)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ValueError(f"הקטגוריה '{normalized_name}' כבר קיימת.") from exc

    await log_action(
        session,
        AuditAction.CATEGORY_CREATED,
        actor_telegram_id=actor_id,
        target_category_id=category.id,
    )
    return category


async def get_all_categories(session: AsyncSession) -> Sequence[Category]:
    """Return categories in a deterministic, case-insensitive display order."""
    result = await session.execute(select(Category).order_by(func.lower(Category.name)))
    return result.scalars().all()


async def get_category_by_id(
    session: AsyncSession, category_id: int
) -> Category | None:
    """Fetch one category by primary key."""
    return await session.get(Category, category_id)


async def delete_category(
    session: AsyncSession, category_id: int, actor_id: int | None = None
) -> int:
    """Return member media to the sorting queue and delete an existing category."""
    result = await session.execute(
        select(Category).where(Category.id == category_id).with_for_update()
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise ValueError("הקטגוריה לא נמצאה.")

    update_result = await session.execute(
        update(Media)
        .where(Media.category_id == category_id)
        .values(category_id=None, status=MediaStatus.WAITING_CATEGORIZATION.value)
    )
    affected_items = update_result.rowcount or 0

    await session.delete(category)
    await session.flush()
    await log_action(
        session,
        AuditAction.CATEGORY_DELETED,
        actor_telegram_id=actor_id,
        target_category_id=category_id,
        details={"restored_media_count": affected_items},
    )
    return affected_items
