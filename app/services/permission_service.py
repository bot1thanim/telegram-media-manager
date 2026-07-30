"""
app/services/permission_service.py
=====================================
Central permission checking service.
All permission logic lives here — never duplicated in handlers.
Implements require_permission() decorator and helper functions.
SRS §7, §7.1
"""

import logging
from collections.abc import Callable
from functools import wraps

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes

from app.database.engine import get_session
from app.database.models.admin import Admin

logger = logging.getLogger(__name__)


class Permission:
    """Permission key constants matching SRS §7.1 JSON keys."""

    IMPORT = "import"
    CATEGORIZE = "categorize"
    PUBLISH = "publish"
    MANAGE_CATEGORIES = "manage_categories"
    MANAGE_TAGS = "manage_tags"
    VIEW_DASHBOARD = "view_dashboard"
    MANAGE_BACKUPS = "manage_backups"


class UserRole:
    OWNER = "owner"
    ADMIN = "admin"
    VIEWER = "viewer"
    UNAUTHORIZED = "unauthorized"


async def get_user_role(
    session: AsyncSession,
    user_id: int,
    owner_id: int,
) -> str:
    """
    Determine the role of a Telegram user.
    Returns one of UserRole constants.
    """
    if user_id == owner_id:
        return UserRole.OWNER

    result = await session.execute(
        select(Admin).where(Admin.telegram_user_id == user_id)
    )
    admin = result.scalar_one_or_none()

    if admin is None:
        return UserRole.UNAUTHORIZED

    return admin.role  # "admin" or "viewer"


async def has_permission(
    session: AsyncSession,
    user_id: int,
    owner_id: int,
    permission: str,
) -> bool:
    """
    Check whether a user has a specific permission.
    Owner always has all permissions.
    Viewer never has any permission (v1).
    Admin has permissions defined in their JSON permissions field.
    """
    role = await get_user_role(session, user_id, owner_id)

    if role == UserRole.OWNER:
        return True

    if role == UserRole.VIEWER:
        return False

    if role == UserRole.UNAUTHORIZED:
        return False

    # Admin — check specific permission
    result = await session.execute(
        select(Admin).where(Admin.telegram_user_id == user_id)
    )
    admin = result.scalar_one_or_none()
    if admin is None:
        return False

    return bool(admin.permissions.get(permission, False))


async def is_authorized(
    session: AsyncSession,
    user_id: int,
    owner_id: int,
) -> bool:
    """Returns True if the user is Owner, Admin, or Viewer (i.e., not completely unauthorized)."""
    role = await get_user_role(session, user_id, owner_id)
    return role != UserRole.UNAUTHORIZED


async def get_admin_record(
    session: AsyncSession,
    user_id: int,
) -> Admin | None:
    """Fetch the Admin record for a user, or None if not found."""
    result = await session.execute(
        select(Admin).where(Admin.telegram_user_id == user_id)
    )
    return result.scalar_one_or_none()


def require_permission(permission: str):
    """
    Decorator for Telegram handlers to enforce permissions.
    SRS §7.1
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(
            update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
        ):
            from app.config import config
            from app.telegram.messages import MSG

            user = update.effective_user
            if not user:
                return

            async with get_session() as session:
                has_perm = await has_permission(
                    session, user.id, config.OWNER_TELEGRAM_ID, permission
                )
                if not has_perm:
                    if update.callback_query:
                        await update.callback_query.answer(
                            MSG.UNAUTHORIZED, show_alert=True
                        )
                    else:
                        await update.message.reply_text(MSG.UNAUTHORIZED)
                    return

            return await func(update, context, *args, **kwargs)

        return wrapper

    return decorator


def owner_only(func: Callable):
    """Decorator for owner-only actions (Settings, Admins)."""

    @wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        from app.config import config
        from app.telegram.messages import MSG

        user = update.effective_user
        if not user or user.id != config.OWNER_TELEGRAM_ID:
            if update.callback_query:
                await update.callback_query.answer(MSG.UNAUTHORIZED, show_alert=True)
            else:
                await update.message.reply_text(MSG.UNAUTHORIZED)
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
