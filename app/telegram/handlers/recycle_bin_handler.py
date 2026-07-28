"""
app/telegram/handlers/recycle_bin_handler.py
==============================================
Handlers for the recycle bin.
SRS §13: Restore, Permanent Delete, Empty Bin.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from app.database.engine import get_session
from app.database.models.media import Media, MediaStatus
from app.services.media_service import restore_from_recycle_bin, permanently_delete_media
from app.telegram.keyboards import CB, recycle_bin_item_keyboard, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


async def list_recycle_bin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Media).where(Media.status == MediaStatus.DELETED.value).order_by(Media.deleted_at.desc())
        )
        items = result.scalars().all()
        
        if not items:
            await query.answer(MSG.RECYCLE_BIN_EMPTY, show_alert=True)
            return
            
        await query.answer()
        # Show the first item in the bin as a sample
        media = items[0]
        caption = f"🗑 פריטים בסל המיחזור: {len(items)}\n\nמציג פריט אחרון שנמחק:\n#{media.id} - {media.caption or 'ללא כיתוב'}"
        
        # Note: Same issue with editing text to media. For simplicity in MVP, we just send text.
        await query.edit_message_text(
            caption,
            reply_markup=recycle_bin_item_keyboard(media.id)
        )


async def restore_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    media_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    
    async with get_session() as session:
        await restore_from_recycle_bin(session, media_id, user_id)
        await query.answer(MSG.RECYCLE_RESTORED)
        await list_recycle_bin(update, context)


async def perm_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    media_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    
    async with get_session() as session:
        await permanently_delete_media(session, media_id, user_id)
        await query.answer(MSG.RECYCLE_PERM_DELETED)
        await list_recycle_bin(update, context)


def register_recycle_bin_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(list_recycle_bin, pattern=f"^{CB.RECYCLE_BIN}$"))
    application.add_handler(CallbackQueryHandler(restore_media_handler, pattern=f"^{CB.REC_RESTORE}"))
    application.add_handler(CallbackQueryHandler(perm_delete_handler, pattern=f"^{CB.REC_PERM_DEL}"))
