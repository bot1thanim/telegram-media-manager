"""
app/telegram/handlers/sorting_handler.py
==========================================
Handlers for the sorting flow.
SRS §10, §10.1, §10.2: Sorting screen, handoff, categorization.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from app.config import config
from app.database.engine import get_session
from app.services.media_service import (
    get_next_media_for_sorting, get_media_by_id, categorize_media, move_to_recycle_bin
)
from app.services.category_service import get_all_categories
from app.services.sorting_service import handle_handoff, confirm_handoff, start_or_update_session, end_session
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import CB, sorting_item_keyboard, category_select_keyboard, handoff_keyboard, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


@require_permission(Permission.CATEGORIZE)
async def start_sorting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggered by 'מיון חדש' or 'המשך מיון'."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    async with get_session() as session:
        # 1. Check for active session (Handoff logic §10.2)
        needs_confirm, active_session = await handle_handoff(session, user_id, update.effective_user.full_name)
        
        if needs_confirm:
            await query.answer()
            await query.edit_message_text(
                MSG.HANDOFF_PROMPT.format(
                    name=active_session.admin_telegram_id, # Should fetch name in real app
                    media_id=active_session.current_media_id
                ),
                reply_markup=handoff_keyboard()
            )
            context.user_data["handoff_media_id"] = active_session.current_media_id
            context.user_data["handoff_old_admin"] = active_session.admin_telegram_id
            return

        # 2. Get next item
        media = None
        if query.data == CB.SORT_RESUME and active_session:
            media = await get_media_by_id(session, active_session.current_media_id)
            
        if not media:
            media = await get_next_media_for_sorting(session)

        if not media:
            await query.answer(MSG.SORT_EMPTY, show_alert=True)
            return

        # 3. Start session
        await start_or_update_session(session, user_id, media.id)
        await _show_sorting_item(update, context, media)


async def _show_sorting_item(update: Update, context: ContextTypes.DEFAULT_TYPE, media) -> None:
    """Display a single media item with sorting controls."""
    query = update.callback_query
    
    caption = MSG.SORT_ITEM_CAPTION.format(
        id=media.id,
        size=round(media.file_size / (1024 * 1024), 2),
        duration_line=MSG.SORT_DURATION_LINE.format(duration=media.duration) if media.duration else "",
        date=media.created_at.strftime("%d/%m/%Y"),
        uploader=media.uploader_name or "Unknown"
    )

    # We must delete the old message and send a new one because we are sending media
    # You cannot 'edit' a text message into a media message in Telegram.
    await query.message.delete()
    
    common_kwargs = {
        "chat_id": update.effective_chat.id,
        "caption": caption,
        "reply_markup": sorting_item_keyboard()
    }

    if media.media_type == "video":
        await context.bot.send_video(video=media.file_id, **common_kwargs)
    elif media.media_type == "photo":
        await context.bot.send_photo(photo=media.file_id, **common_kwargs)
    elif media.media_type == "animation":
        await context.bot.send_animation(animation=media.file_id, **common_kwargs)
    else:
        await context.bot.send_document(document=media.file_id, **common_kwargs)


async def sort_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles buttons: Save, Skip, Delete, Next, Prev."""
    query = update.callback_query
    action = query.data
    user_id = update.effective_user.id

    async with get_session() as session:
        # Get current session to know which media we are on
        # In a real app, we'd extract media_id from the caption or callback_data
        # For this MVP, we assume the session tracking is enough
        result = await session.execute(
            select(SortingSession).where(SortingSession.admin_telegram_id == user_id)
        )
        active = result.scalar_one_or_none()
        if not active:
            await query.answer(MSG.NO_ACTIVE_SESSION)
            return

        media_id = active.current_media_id

        if action == CB.SORT_SAVE:
            # Show category selection
            categories = await get_all_categories(session)
            await query.answer()
            # Since we are on a media message, we can't edit text. 
            # We send a new message for category selection.
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=MSG.SORT_CHOOSE_CATEGORY,
                reply_markup=category_select_keyboard(categories)
            )
            return

        elif action == CB.SORT_DELETE:
            await move_to_recycle_bin(session, media_id, user_id)
            await query.answer(MSG.SORT_DELETED)
            # Move to next
            next_media = await get_next_media_for_sorting(session)
            if next_media:
                await start_or_update_session(session, user_id, next_media.id)
                await _show_sorting_item(update, context, next_media)
            else:
                await end_session(session, user_id)
                await context.bot.send_message(update.effective_chat.id, MSG.SORT_EMPTY)
            return

        elif action == CB.SORT_SKIP or action == CB.SORT_NEXT:
            next_media = await get_next_media_for_sorting(session, exclude_ids=[media_id])
            if next_media:
                await start_or_update_session(session, user_id, next_media.id)
                await _show_sorting_item(update, context, next_media)
            else:
                await query.answer(MSG.SORT_EMPTY)
            return


async def category_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the actual saving to a category."""
    query = update.callback_query
    category_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id

    async with get_session() as session:
        result = await session.execute(
            select(SortingSession).where(SortingSession.admin_telegram_id == user_id)
        )
        active = result.scalar_one_or_none()
        if not active:
            await query.answer(MSG.NO_ACTIVE_SESSION)
            return

        media = await categorize_media(session, active.current_media_id, category_id, user_id)
        category = await session.get(Category, category_id)
        
        await query.answer(MSG.SORT_SAVED.format(category_name=category.name))
        
        # Move to next
        next_media = await get_next_media_for_sorting(session)
        if next_media:
            await start_or_update_session(session, user_id, next_media.id)
            await _show_sorting_item(update, context, next_media)
        else:
            await end_session(session, user_id)
            await query.edit_message_text(MSG.SORT_EMPTY, reply_markup=main_menu_keyboard())


def register_sorting_handlers(application) -> None:
    from sqlalchemy import select
    from app.database.models.sorting_session import SortingSession
    
    application.add_handler(CallbackQueryHandler(start_sorting, pattern=f"^{CB.SORT_NEW}$|^{CB.SORT_RESUME}$"))
    application.add_handler(CallbackQueryHandler(sort_action_handler, pattern=f"^{CB.SORT_SAVE}$|^{CB.SORT_SKIP}$|^{CB.SORT_DELETE}$|^{CB.SORT_NEXT}$"))
    application.add_handler(CallbackQueryHandler(category_selection_handler, pattern=f"^{CB.SORT_CAT_SELECT}"))
