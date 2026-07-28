"""
app/telegram/handlers/backup_handler.py
=========================================
Handlers for backup and restore.
SRS §19: JSON backup, restore from file.
"""

import io
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from app.database.engine import get_session
from app.backup.service import create_backup, restore_backup
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import CB, backup_keyboard, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


@require_permission(Permission.MANAGE_BACKUPS)
async def show_backup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💾 תפריט גיבוי ושחזור:", reply_markup=backup_keyboard())


async def run_backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    
    async with get_session() as session:
        json_data = await create_backup(session, actor_id=user_id)
        
        # Send as file
        bio = io.BytesIO(json_data.encode('utf-8'))
        bio.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        await query.answer("הגיבוי נוצר!")
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=bio,
            caption=MSG.BACKUP_COMPLETED
        )


async def prompt_restore_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("אנא שלח את קובץ ה-JSON של הגיבוי שברצונך לשחזר.")
    context.user_data["awaiting_backup_file"] = True


async def handle_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("awaiting_backup_file") or not update.message.document:
        return
        
    user_id = update.effective_user.id
    file = await update.message.document.get_file()
    content = await file.download_as_bytearray()
    json_data = content.decode('utf-8')
    
    async with get_session() as session:
        try:
            await restore_backup(session, json_data, actor_id=user_id)
            context.user_data["awaiting_backup_file"] = False
            await update.message.reply_text("✅ השחזור הושלם בהצלחה!", reply_markup=main_menu_keyboard())
        except Exception as e:
            logger.exception("Restore failed")
            await update.message.reply_text(f"❌ השחזור נכשל: {str(e)}")


def register_backup_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(show_backup_menu, pattern=f"^{CB.BACKUP}$"))
    application.add_handler(CallbackQueryHandler(run_backup_handler, pattern=f"^{CB.BACKUP_NOW}$"))
    application.add_handler(CallbackQueryHandler(prompt_restore_backup, pattern=f"^{CB.BACKUP_RESTORE}$"))
    application.add_handler(MessageHandler(filters.Document.JSON, handle_backup_file))
