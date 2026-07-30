"""Handlers for admin management: listing, adding, and removing non-owner users."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.audit.logger import AuditAction, log_action
from app.database.engine import get_session
from app.database.models.admin import Admin, AdminRole
from app.services.permission_service import owner_only
from app.telegram.keyboards import CB, admins_keyboard, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


@owner_only
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display a list of current admins and options to add/remove them."""
    query = update.callback_query

    async with get_session() as session:
        from sqlalchemy import select

        result = await session.execute(select(Admin))
        admins = result.scalars().all()

        text = MSG.ADMINS_MENU + "\n\n"
        if not admins:
            text += "אין מנהלים רשומים כרגע.\n"
        else:
            for admin in admins:
                text += f"• {admin.display_name or 'Admin'} (`{admin.telegram_user_id}`) - {admin.role}\n"

        await query.answer()
        await query.edit_message_text(
            text, reply_markup=admins_keyboard(admins), parse_mode="Markdown"
        )


@owner_only
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt the owner to forward a message from the user to be added as admin."""
    query = update.callback_query
    try:
        role_str = query.data.removeprefix(f"{CB.ADM_ADD}:")
        role = AdminRole(role_str)
    except ValueError:
        await query.answer(MSG.ERROR_GENERIC, show_alert=True)
        return

    context.user_data["awaiting_admin_add"] = role.value
    await query.answer()
    await query.edit_message_text(
        MSG.ADD_ADMIN_PROMPT.format(role=role.value),
        reply_markup=main_menu_keyboard(),
    )


@owner_only
async def handle_add_admin_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Process the forwarded message to add a new admin."""
    role_to_add = context.user_data.pop("awaiting_admin_add", None)
    if role_to_add not in [AdminRole.ADMIN.value, AdminRole.VIEWER.value]:
        return

    message = update.effective_message
    if message is None or message.forward_from is None:
        await message.reply_text(MSG.ADD_ADMIN_INVALID_FORWARD)
        return

    new_admin_id = message.forward_from.id
    new_admin_display_name = message.forward_from.full_name
    new_admin_username = message.forward_from.username
    owner_id = update.effective_user.id

    async with get_session() as session:
        from sqlalchemy import select

        existing_admin = await session.execute(
            select(Admin).where(Admin.telegram_user_id == new_admin_id)
        )
        if existing_admin.scalar_one_or_none():
            await message.reply_text(MSG.ADD_ADMIN_ALREADY_EXISTS)
            return

        admin = Admin(
            telegram_user_id=new_admin_id,
            display_name=new_admin_display_name,
            username=new_admin_username,
            role=role_to_add,
            added_by_user_id=owner_id,
        )
        session.add(admin)
        await session.commit()
        await log_action(
            session,
            AuditAction.ADMIN_ADDED,
            actor_telegram_id=owner_id,
            details={
                "new_admin_id": new_admin_id,
                "new_admin_role": role_to_add,
            },
        )
        await message.reply_text(
            MSG.ADD_ADMIN_SUCCESS.format(name=new_admin_display_name, role=role_to_add)
        )


@owner_only
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove an admin from the system."""
    query = update.callback_query
    try:
        admin_id_to_remove = int(query.data.removeprefix(CB.ADM_REMOVE))
    except ValueError:
        await query.answer(MSG.ERROR_GENERIC, show_alert=True)
        return

    owner_id = update.effective_user.id

    async with get_session() as session:
        from sqlalchemy import delete, select

        admin = await session.execute(
            select(Admin).where(Admin.id == admin_id_to_remove)
        )
        admin_obj = admin.scalar_one_or_none()

        if not admin_obj:
            await query.answer(MSG.REMOVE_ADMIN_NOT_FOUND, show_alert=True)
            return

        await session.execute(delete(Admin).where(Admin.id == admin_id_to_remove))
        await session.commit()
        await log_action(
            session,
            AuditAction.ADMIN_REMOVED,
            actor_telegram_id=owner_id,
            details={
                "removed_admin_id": admin_obj.telegram_user_id,
                "removed_admin_role": admin_obj.role,
            },
        )
        await query.answer(
            MSG.REMOVE_ADMIN_SUCCESS.format(
                name=admin_obj.display_name
                or admin_obj.username
                or str(admin_obj.telegram_user_id)
            )
        )
        await list_admins(update, context)  # Refresh the admin list


def register_admin_handlers(application) -> None:
    """Register admin management handlers with the PTB Application."""
    application.add_handler(CallbackQueryHandler(list_admins, pattern=f"^{CB.ADMINS}$"))
    application.add_handler(
        CallbackQueryHandler(add_admin, pattern=f"^{CB.ADM_ADD}.*$")
    )
    application.add_handler(
        CallbackQueryHandler(remove_admin, pattern=f"^{CB.ADM_REMOVE}.*$")
    )
    # This handler needs to be added to the main application loop to catch forwarded messages
    # It should be placed after other message handlers to avoid conflicts
    # For now, it's not directly registered here, but will be part of the main app setup.
    # MessageHandler(filters.FORWARDED & filters.User(config.OWNER_TELEGRAM_ID), handle_add_admin_message)
