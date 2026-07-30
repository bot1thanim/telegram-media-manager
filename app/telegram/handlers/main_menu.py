"""Handlers for access-gated main-menu and media-management navigation."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.audit.logger import AuditAction, log_action
from app.config import config
from app.database.engine import get_session
from app.database.models.duplicate_group import DuplicateGroupStatus
from app.services.permission_service import (
    Permission,
    UserRole,
    get_user_role,
    is_authorized,
    require_permission,
)
from app.telegram.keyboards import CB, main_menu_keyboard, media_mgmt_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


async def _count_pending_duplicates(session) -> int:
    from sqlalchemy import func, select

    from app.database.models.duplicate_group import DuplicateGroup

    result = await session.execute(
        select(func.count()).where(
            DuplicateGroup.status == DuplicateGroupStatus.PENDING_REVIEW.value
        )
    )
    return result.scalar_one() or 0


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display a role-gated main menu for commands and callback navigation."""
    del context
    user = update.effective_user
    if user is None:
        return

    async with get_session() as session:
        role = await get_user_role(session, user.id, config.OWNER_TELEGRAM_ID)
        if role == UserRole.UNAUTHORIZED:
            await log_action(
                session,
                AuditAction.UNAUTHORIZED_ACCESS_ATTEMPT,
                actor_telegram_id=user.id,
                details={"action": "main_menu"},
            )
            text = MSG.UNAUTHORIZED
            if update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text(text)
            return

        if role == UserRole.VIEWER:
            text = MSG.VIEWER_NOT_AVAILABLE
            if update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text(text)
            return

        keyboard = main_menu_keyboard(
            is_owner=role == UserRole.OWNER,
            pending_duplicates=await _count_pending_duplicates(session),
        )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            MSG.MAIN_MENU_WELCOME,
            reply_markup=keyboard,
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            MSG.MAIN_MENU_WELCOME,
            reply_markup=keyboard,
        )


@require_permission(Permission.CATEGORIZE)
async def show_media_management(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Open the supported media-sorting actions for an authorized user."""
    del context
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎬 ניהול מדיה\n\nבחר פעולה:",
        reply_markup=media_mgmt_keyboard(),
    )


async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return a minimal liveness response to an authorized user."""
    del context
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return

    async with get_session() as session:
        authorized = await is_authorized(session, user.id, config.OWNER_TELEGRAM_ID)
        if not authorized:
            await log_action(
                session,
                AuditAction.UNAUTHORIZED_ACCESS_ATTEMPT,
                actor_telegram_id=user.id,
                details={"action": "ping"},
            )
            await message.reply_text(MSG.UNAUTHORIZED)
            return

    await message.reply_text(MSG.PONG)


def register_main_menu_handlers(application) -> None:
    """Register commands and the main navigation callback contract."""
    application.add_handler(CommandHandler("start", show_main_menu))
    application.add_handler(CommandHandler("menu", show_main_menu))
    application.add_handler(CommandHandler("ping", ping_handler))
    application.add_handler(
        CallbackQueryHandler(show_main_menu, pattern=f"^{CB.MAIN_MENU}$")
    )
    application.add_handler(
        CallbackQueryHandler(show_media_management, pattern=f"^{CB.MEDIA_MGMT}$")
    )
