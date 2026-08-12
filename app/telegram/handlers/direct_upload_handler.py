"""Owner/Admin direct upload flow for a category selected in the bot UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.database.engine import get_session
from app.services.category_service import get_all_categories, get_category_by_id
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import (
    CB,
    category_select_keyboard,
    direct_upload_prompt_keyboard,
    media_mgmt_keyboard,
)

_UPLOAD_CATEGORY_KEY = "direct_upload_category_id"
_UPLOAD_STARTED_AT_KEY = "direct_upload_started_at"
_UPLOAD_TTL = timedelta(hours=12)


def get_pending_upload_category_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Return a non-expired selected category for the current Telegram user."""
    raw_category_id = context.user_data.get(_UPLOAD_CATEGORY_KEY)
    started_at = context.user_data.get(_UPLOAD_STARTED_AT_KEY)
    if not isinstance(raw_category_id, int) or not isinstance(started_at, datetime):
        return None
    if datetime.now(timezone.utc) - started_at > _UPLOAD_TTL:
        clear_pending_upload_category(context)
        return None
    return raw_category_id


def clear_pending_upload_category(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear all transient direct-upload state for the current Telegram user."""
    context.user_data.pop(_UPLOAD_CATEGORY_KEY, None)
    context.user_data.pop(_UPLOAD_STARTED_AT_KEY, None)


@require_permission(Permission.IMPORT)
async def prompt_direct_upload_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Render a paginated category picker for the direct-upload flow."""
    query = update.callback_query
    async with get_session() as session:
        categories = await get_all_categories(session)
    if not categories:
        await query.answer("אין קטגוריות פעילות לבחירה.", show_alert=True)
        return
    clear_pending_upload_category(context)
    await query.answer()
    await query.edit_message_text(
        "בחר קטגוריה להעלאה. לאחר הבחירה שלח לבוט בפרטי סרטונים, תמונות או קבצים.",
        reply_markup=category_select_keyboard(
            categories,
            back_cb=CB.MEDIA_MGMT,
            select_prefix=CB.DIRECT_UPLOAD_CATEGORY,
            page_prefix=CB.DIRECT_UPLOAD_PAGE,
            include_create=False,
        ),
    )


@require_permission(Permission.IMPORT)
async def show_direct_upload_category_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Render a validated page in the direct-upload category picker."""
    query = update.callback_query
    try:
        page = max(0, int(query.data.removeprefix(CB.DIRECT_UPLOAD_PAGE)))
    except ValueError:
        await query.answer("מספר עמוד לא תקין.", show_alert=True)
        return
    async with get_session() as session:
        categories = await get_all_categories(session)
    await query.answer()
    await query.edit_message_reply_markup(
        reply_markup=category_select_keyboard(
            categories,
            page=page,
            back_cb=CB.MEDIA_MGMT,
            select_prefix=CB.DIRECT_UPLOAD_CATEGORY,
            page_prefix=CB.DIRECT_UPLOAD_PAGE,
            include_create=False,
        )
    )


@require_permission(Permission.IMPORT)
async def select_direct_upload_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Validate selection and arm the user's private-media upload target."""
    query = update.callback_query
    try:
        category_id = int(query.data.removeprefix(CB.DIRECT_UPLOAD_CATEGORY))
    except ValueError:
        await query.answer("בחירת קטגוריה לא תקינה.", show_alert=True)
        return

    async with get_session() as session:
        category = await get_category_by_id(session, category_id)
    if category is None:
        await query.answer("הקטגוריה אינה קיימת או נמחקה.", show_alert=True)
        return

    context.user_data[_UPLOAD_CATEGORY_KEY] = category.id
    context.user_data[_UPLOAD_STARTED_AT_KEY] = datetime.now(timezone.utc)
    await query.answer(f"נבחרה הקטגוריה: {category.name}")
    await query.edit_message_text(
        f"⬆️ מצב העלאה פעיל: **{category.name}**\n\n"
        "שלח עכשיו לבוט בפרטי סרטונים, תמונות או קבצים. כל פריט חדש יישמר "
        "ישירות בקטגוריה הזו ויהיה מוכן לפרסום.",
        parse_mode="Markdown",
        reply_markup=direct_upload_prompt_keyboard(),
    )


@require_permission(Permission.IMPORT)
async def cancel_direct_upload(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """End the selected-category upload mode without modifying stored media."""
    query = update.callback_query
    clear_pending_upload_category(context)
    await query.answer("מצב העלאה הסתיים.")
    await query.edit_message_text(
        "🎬 ניהול מדיה\n\nבחר פעולה:", reply_markup=media_mgmt_keyboard()
    )


def register_direct_upload_handlers(application) -> None:
    """Register direct-upload callbacks before generic media imports are processed."""
    application.add_handler(
        CallbackQueryHandler(
            prompt_direct_upload_category, pattern=f"^{CB.DIRECT_UPLOAD}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            show_direct_upload_category_page,
            pattern=f"^{CB.DIRECT_UPLOAD_PAGE}\\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            select_direct_upload_category,
            pattern=f"^{CB.DIRECT_UPLOAD_CATEGORY}\\d+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(cancel_direct_upload, pattern=f"^{CB.DIRECT_UPLOAD_CANCEL}$")
    )
