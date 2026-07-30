"""Secure category creation, listing and deletion handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.config import config
from app.database.engine import get_session
from app.services.category_service import (
    create_category,
    delete_category,
    get_all_categories,
    get_category_by_id,
)
from app.services.permission_service import (
    Permission,
    has_permission,
    require_permission,
)
from app.telegram.keyboards import (
    CB,
    categories_list_keyboard,
    category_actions_keyboard,
    confirm_keyboard,
    main_menu_keyboard,
)
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


def _callback_id(data: str, prefix: str) -> int | None:
    raw_value = data.removeprefix(prefix)
    return int(raw_value) if raw_value.isdigit() else None


@require_permission(Permission.MANAGE_CATEGORIES)
async def list_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display a validated page of categories."""
    del context
    query = update.callback_query
    page = 0
    if query.data.startswith(CB.CAT_PAGE):
        raw_page = query.data.removeprefix(CB.CAT_PAGE)
        if not raw_page.isdigit():
            await query.answer("מספר עמוד לא תקין.", show_alert=True)
            return
        page = int(raw_page)

    async with get_session() as session:
        categories = await get_all_categories(session)
    await query.answer()
    await query.edit_message_text(
        MSG.CATEGORIES_MENU,
        reply_markup=categories_list_keyboard(categories, page=page),
    )


@require_permission(Permission.MANAGE_CATEGORIES)
async def category_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display supported actions for one existing category."""
    query = update.callback_query
    category_id = _callback_id(query.data, "cat_detail:")
    if category_id is None:
        await query.answer("בחירת נושא לא תקינה.", show_alert=True)
        return

    async with get_session() as session:
        category = await get_category_by_id(session, category_id)
    if category is None:
        await query.answer(MSG.CATEGORY_NOT_FOUND, show_alert=True)
        return

    emoji = category.emoji or "📁"
    text = f"{emoji} **{category.name}**\n"
    if category.telegram_thread_id:
        text += f"🔗 מקושר ל־Topic ID: {category.telegram_thread_id}"
    else:
        text += "⚠️ לא מקושר ל־Topic"
    await query.answer()
    await query.edit_message_text(
        text,
        reply_markup=category_actions_keyboard(category_id),
        parse_mode="Markdown",
    )


@require_permission(Permission.MANAGE_CATEGORIES)
async def prompt_create_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Ask an authorized user for a validated new category name."""
    query = update.callback_query
    context.user_data["awaiting_category_name"] = True
    await query.answer()
    await query.edit_message_text(MSG.CATEGORY_CREATE_NAME_PROMPT)


async def handle_category_name_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Process a category name only for the user who opened the create flow."""
    # This generic text handler is registered before the publishing handler, so
    # dispatch a pending scheduled-time input before deciding whether text is a
    # category name.
    from app.telegram.handlers.publish_handler import handle_schedule_time_input

    if await handle_schedule_time_input(update, context):
        return
    if not context.user_data.get("awaiting_category_name"):
        return

    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return

    async with get_session() as session:
        allowed = await has_permission(
            session,
            user.id,
            config.OWNER_TELEGRAM_ID,
            Permission.MANAGE_CATEGORIES,
        )
        if not allowed:
            context.user_data.pop("awaiting_category_name", None)
            await message.reply_text(MSG.UNAUTHORIZED)
            return
        try:
            category = await create_category(
                session, message.text or "", actor_id=user.id
            )
        except ValueError as exc:
            await message.reply_text(str(exc))
            return

    context.user_data.pop("awaiting_category_name", None)
    await message.reply_text(
        f"✅ הקטגוריה '{category.name}' נוצרה בהצלחה.",
        reply_markup=main_menu_keyboard(),
    )


@require_permission(Permission.MANAGE_CATEGORIES)
async def prompt_delete_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Render a deletion confirmation only for an existing category."""
    query = update.callback_query
    category_id = _callback_id(query.data, CB.CAT_DELETE)
    if category_id is None:
        await query.answer("בחירת נושא לא תקינה.", show_alert=True)
        return

    async with get_session() as session:
        category = await get_category_by_id(session, category_id)
        if category is None:
            await query.answer(MSG.CATEGORY_NOT_FOUND, show_alert=True)
            return
        from sqlalchemy import func, select

        from app.database.models.media import Media

        result = await session.execute(
            select(func.count()).where(Media.category_id == category_id)
        )
        count = result.scalar_one()

    text = MSG.CONFIRM_TEMPLATE.format(
        description=MSG.CONFIRM_DELETE_CATEGORY.format(count=count),
        details=f"שם הקטגוריה: {category.name}",
    )
    await query.answer()
    await query.edit_message_text(
        text,
        reply_markup=confirm_keyboard(
            yes_cb=f"cat_del_confirm:{category_id}",
            no_cb=f"cat_detail:{category_id}",
        ),
    )


@require_permission(Permission.MANAGE_CATEGORIES)
async def confirm_delete_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Delete a category atomically, restoring its media to the sorting queue."""
    query = update.callback_query
    category_id = _callback_id(query.data, "cat_del_confirm:")
    if category_id is None:
        await query.answer("בחירת נושא לא תקינה.", show_alert=True)
        return

    try:
        async with get_session() as session:
            count = await delete_category(
                session,
                category_id,
                actor_id=update.effective_user.id,
            )
    except ValueError:
        await query.answer(MSG.CATEGORY_NOT_FOUND, show_alert=True)
        return

    await query.answer(MSG.CATEGORY_DELETED.format(count=count), show_alert=True)
    await list_categories(update, context)


def register_category_handlers(application) -> None:
    """Register strict callback patterns and a single text-flow dispatcher."""
    application.add_handler(
        CallbackQueryHandler(
            list_categories,
            pattern=f"^(?:{CB.TOPICS}|{CB.CAT_PAGE}\\d+)$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(category_detail, pattern=r"^cat_detail:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(prompt_create_category, pattern=f"^{CB.CAT_NEW}$")
    )
    application.add_handler(
        CallbackQueryHandler(prompt_delete_category, pattern=f"^{CB.CAT_DELETE}\\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(confirm_delete_category, pattern=r"^cat_del_confirm:\d+$")
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_name_input)
    )
