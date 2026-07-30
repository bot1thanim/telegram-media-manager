"""Permission-protected Telegram handlers for JSON backup and recovery."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.backup.service import create_backup, restore_backup
from app.database.engine import get_session
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import CB, backup_keyboard, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)
MAX_BACKUP_FILE_BYTES = 10 * 1024 * 1024


@require_permission(Permission.MANAGE_BACKUPS)
async def show_backup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the backup and recovery menu."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💾 תפריט גיבוי ושחזור:", reply_markup=backup_keyboard()
    )


@require_permission(Permission.MANAGE_BACKUPS)
async def run_backup_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generate a bounded JSON backup and deliver it only to the authorized user."""
    query = update.callback_query
    user_id = update.effective_user.id
    async with get_session() as session:
        json_data = await create_backup(session, actor_id=user_id)

    payload = json_data.encode("utf-8")
    if len(payload) > MAX_BACKUP_FILE_BYTES:
        logger.error("Generated backup for user %d exceeds delivery limit", user_id)
        await query.answer("הגיבוי גדול מדי לשליחה דרך Telegram.", show_alert=True)
        return

    document = io.BytesIO(payload)
    document.name = (
        f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    await query.answer("הגיבוי נוצר!")
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=document,
        caption=MSG.BACKUP_COMPLETED,
    )


@require_permission(Permission.MANAGE_BACKUPS)
async def prompt_restore_backup(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Enter a one-use, user-scoped restore-upload state."""
    query = update.callback_query
    context.user_data["awaiting_backup_file"] = True
    await query.answer()
    await query.edit_message_text("אנא שלח את קובץ ה־JSON של הגיבוי שברצונך לשחזר.")


@require_permission(Permission.MANAGE_BACKUPS)
async def handle_backup_file(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Validate and restore an explicitly requested JSON file without leaking errors."""
    if not context.user_data.get("awaiting_backup_file") or not update.message.document:
        return

    document = update.message.document
    context.user_data["awaiting_backup_file"] = False
    if document.file_size is not None and document.file_size > MAX_BACKUP_FILE_BYTES:
        await update.message.reply_text("❌ קובץ הגיבוי גדול מהמגבלה המותרת.")
        return

    try:
        telegram_file = await document.get_file()
        content = await telegram_file.download_as_bytearray()
        if len(content) > MAX_BACKUP_FILE_BYTES:
            raise ValueError("Backup exceeds the allowed size.")
        json_data = bytes(content).decode("utf-8")
        async with get_session() as session:
            categories_count, media_count = await restore_backup(
                session,
                json_data,
                actor_id=update.effective_user.id,
            )
    except UnicodeDecodeError:
        await update.message.reply_text("❌ קובץ הגיבוי חייב להיות JSON בקידוד UTF‑8.")
    except (TypeError, ValueError) as exc:
        logger.warning(
            "Rejected backup restore for user %d: %s", update.effective_user.id, exc
        )
        await update.message.reply_text("❌ קובץ הגיבוי אינו תקין או אינו נתמך.")
    except Exception:
        logger.exception("Backup restore failed")
        await update.message.reply_text(
            "❌ השחזור נכשל. הפעולה תועדה; נסה שוב מאוחר יותר."
        )
    else:
        await update.message.reply_text(
            f"✅ השחזור הושלם: {categories_count} קטגוריות ו־{media_count} פריטי מדיה.",
            reply_markup=main_menu_keyboard(),
        )


def register_backup_handlers(application) -> None:
    application.add_handler(
        CallbackQueryHandler(show_backup_menu, pattern=f"^{CB.BACKUP}$")
    )
    application.add_handler(
        CallbackQueryHandler(run_backup_handler, pattern=f"^{CB.BACKUP_NOW}$")
    )
    application.add_handler(
        CallbackQueryHandler(prompt_restore_backup, pattern=f"^{CB.BACKUP_RESTORE}$")
    )
    application.add_handler(MessageHandler(filters.Document.ALL, handle_backup_file))
