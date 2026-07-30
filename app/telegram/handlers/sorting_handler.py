"""Telegram handlers for the controlled media-sorting workflow."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.database.engine import get_session
from app.database.models.category import Category
from app.services.category_service import get_all_categories
from app.services.media_service import (
    categorize_media,
    get_media_by_id,
    get_next_media_for_sorting,
    move_to_recycle_bin,
)
from app.services.permission_service import Permission, require_permission
from app.services.sorting_service import (
    confirm_handoff,
    end_session,
    get_session_for_admin,
    handle_handoff,
    start_or_update_session,
)
from app.telegram.keyboards import (
    CB,
    category_select_keyboard,
    handoff_keyboard,
    main_menu_keyboard,
    sorting_item_keyboard,
)
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


@require_permission(Permission.CATEGORIZE)
async def start_sorting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a new session or resume the requester's current media item."""
    query = update.callback_query
    user_id = update.effective_user.id

    async with get_session() as session:
        needs_confirm, active_session = await handle_handoff(
            session, user_id, update.effective_user.full_name
        )
        if needs_confirm and active_session is not None:
            context.user_data["handoff_media_id"] = active_session.current_media_id
            context.user_data["handoff_old_admin"] = active_session.admin_telegram_id
            await query.answer()
            await query.edit_message_text(
                MSG.HANDOFF_PROMPT.format(
                    name=active_session.admin_telegram_id,
                    media_id=active_session.current_media_id,
                ),
                reply_markup=handoff_keyboard(),
            )
            return

        media = None
        if query.data == CB.SORT_RESUME and active_session is not None:
            media = await get_media_by_id(session, active_session.current_media_id)
        if media is None:
            media = await get_next_media_for_sorting(session)
        if media is None:
            await query.answer(MSG.SORT_EMPTY, show_alert=True)
            return

        await start_or_update_session(session, user_id, media.id)
        await query.answer()
        await _show_sorting_item(update, context, media)


@require_permission(Permission.CATEGORIZE)
async def confirm_handoff_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Transfer an active sorting session only after explicit confirmation."""
    query = update.callback_query
    user_id = update.effective_user.id
    media_id = context.user_data.pop("handoff_media_id", None)
    old_admin_id = context.user_data.pop("handoff_old_admin", None)
    if not isinstance(media_id, int) or not isinstance(old_admin_id, int):
        await query.answer(MSG.NO_ACTIVE_SESSION, show_alert=True)
        return

    async with get_session() as session:
        media = await get_media_by_id(session, media_id)
        if media is None:
            await query.answer(MSG.SORT_CONCURRENT_CONFLICT, show_alert=True)
            return
        await confirm_handoff(session, user_id, old_admin_id, media_id)
        await query.answer()
        await _show_sorting_item(update, context, media)


@require_permission(Permission.CATEGORIZE)
async def cancel_handoff_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Clear pending handoff state and return safely to the main menu."""
    query = update.callback_query
    context.user_data.pop("handoff_media_id", None)
    context.user_data.pop("handoff_old_admin", None)
    await query.answer(MSG.CANCELLED)
    await query.edit_message_text(
        MSG.MAIN_MENU_WELCOME, reply_markup=main_menu_keyboard()
    )


async def _show_sorting_item(
    update: Update, context: ContextTypes.DEFAULT_TYPE, media
) -> None:
    """Replace the previous control message with the selected Telegram media item."""
    query = update.callback_query
    size_megabytes = (media.file_size_bytes or 0) / (1024 * 1024)
    duration_line = (
        MSG.SORT_DURATION_LINE.format(duration=media.duration_seconds)
        if media.duration_seconds is not None
        else ""
    )
    caption = MSG.SORT_ITEM_CAPTION.format(
        id=media.id,
        size=round(size_megabytes, 2),
        duration_line=duration_line,
        date=media.created_at.strftime("%d/%m/%Y"),
        uploader=str(media.uploaded_by_user_id or "Unknown"),
    )

    try:
        await query.message.delete()
    except Exception:
        logger.debug("Previous sorting message was already unavailable", exc_info=True)

    common_kwargs = {
        "chat_id": update.effective_chat.id,
        "caption": caption,
        "reply_markup": sorting_item_keyboard(),
    }
    if media.media_type == "video":
        await context.bot.send_video(video=media.file_id, **common_kwargs)
    elif media.media_type == "photo":
        await context.bot.send_photo(photo=media.file_id, **common_kwargs)
    else:
        await context.bot.send_document(document=media.file_id, **common_kwargs)


@require_permission(Permission.CATEGORIZE)
async def sort_action_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle saving, skipping, deleting and advancing the active media item."""
    query = update.callback_query
    action = query.data
    user_id = update.effective_user.id

    async with get_session() as session:
        active = await get_session_for_admin(session, user_id)
        if active is None or active.current_media_id is None:
            await query.answer(MSG.NO_ACTIVE_SESSION, show_alert=True)
            return
        media_id = active.current_media_id

        if action == CB.SORT_SAVE:
            categories = await get_all_categories(session)
            await query.answer()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=MSG.SORT_CHOOSE_CATEGORY,
                reply_markup=category_select_keyboard(categories, include_create=False),
            )
            return

        if action == CB.SORT_DELETE:
            await move_to_recycle_bin(session, media_id, user_id)
            await query.answer(MSG.SORT_DELETED)
        elif action in {CB.SORT_SKIP, CB.SORT_NEXT}:
            await query.answer()
        else:
            await query.answer(MSG.ERROR_GENERIC, show_alert=True)
            return

        next_media = await get_next_media_for_sorting(session, exclude_ids=[media_id])
        if next_media is None:
            await end_session(session, user_id)
            await context.bot.send_message(update.effective_chat.id, MSG.SORT_EMPTY)
            return
        await start_or_update_session(session, user_id, next_media.id)
        await _show_sorting_item(update, context, next_media)


@require_permission(Permission.CATEGORIZE)
async def show_category_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Render a requested category page for the active sorting session."""
    query = update.callback_query
    try:
        page = max(0, int(query.data.removeprefix(CB.SORT_PAGE)))
    except ValueError:
        await query.answer(MSG.ERROR_GENERIC, show_alert=True)
        return
    async with get_session() as session:
        categories = await get_all_categories(session)
    await query.answer()
    await query.edit_message_reply_markup(
        reply_markup=category_select_keyboard(
            categories, page=page, include_create=False
        )
    )


@require_permission(Permission.CATEGORIZE)
async def return_to_current_sort_item(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Return from category selection to the media owned by the requester."""
    query = update.callback_query
    user_id = update.effective_user.id
    async with get_session() as session:
        active = await get_session_for_admin(session, user_id)
        media = (
            await get_media_by_id(session, active.current_media_id)
            if active is not None and active.current_media_id is not None
            else None
        )
    if media is None:
        await query.answer(MSG.NO_ACTIVE_SESSION, show_alert=True)
        return
    await query.answer()
    await _show_sorting_item(update, context, media)


@require_permission(Permission.CATEGORIZE)
async def category_selection_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Categorize the current item, then safely advance the session."""
    query = update.callback_query
    user_id = update.effective_user.id
    try:
        category_id = int(query.data.removeprefix(CB.SORT_CAT_SELECT))
    except ValueError:
        await query.answer(MSG.ERROR_GENERIC, show_alert=True)
        return

    async with get_session() as session:
        active = await get_session_for_admin(session, user_id)
        if active is None or active.current_media_id is None:
            await query.answer(MSG.NO_ACTIVE_SESSION, show_alert=True)
            return
        try:
            await categorize_media(
                session, active.current_media_id, category_id, user_id
            )
        except ValueError:
            await query.answer(MSG.SORT_CONCURRENT_CONFLICT, show_alert=True)
            return
        category = await session.get(Category, category_id)
        await query.answer(
            MSG.SORT_SAVED.format(
                category_name=category.name if category else str(category_id)
            )
        )
        next_media = await get_next_media_for_sorting(session)
        if next_media is None:
            await end_session(session, user_id)
            await query.edit_message_text(
                MSG.SORT_EMPTY, reply_markup=main_menu_keyboard()
            )
            return
        await start_or_update_session(session, user_id, next_media.id)
        await _show_sorting_item(update, context, next_media)


def register_sorting_handlers(application) -> None:
    application.add_handler(
        CallbackQueryHandler(
            start_sorting, pattern=f"^{CB.SORT_NEW}$|^{CB.SORT_RESUME}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(confirm_handoff_handler, pattern=f"^{CB.HANDOFF_CONFIRM}$")
    )
    application.add_handler(
        CallbackQueryHandler(cancel_handoff_handler, pattern=f"^{CB.HANDOFF_CANCEL}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            sort_action_handler,
            pattern=f"^{CB.SORT_SAVE}$|^{CB.SORT_SKIP}$|^{CB.SORT_DELETE}$|^{CB.SORT_NEXT}$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            category_selection_handler, pattern=f"^{CB.SORT_CAT_SELECT}"
        )
    )
    application.add_handler(
        CallbackQueryHandler(show_category_page, pattern=f"^{CB.SORT_PAGE}")
    )
    application.add_handler(
        CallbackQueryHandler(
            return_to_current_sort_item, pattern=f"^{CB.SORT_CAT_BACK}$"
        )
    )
