"""
app/telegram/handlers/import_handler.py
=========================================
Handles incoming media messages from the group or DM.
SRS §9, §9.1: Automatic import, duplicate check.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.config import config
from app.database.engine import get_session
from app.services.media_service import import_media
from app.services.permission_service import has_permission, Permission
from app.duplicate_detector.detector import scan_for_duplicates, create_duplicate_group
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


async def media_import_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for all incoming media.
    Checks permissions, imports to DB, and triggers duplicate scan.
    """
    message = update.effective_message
    if not message:
        return

    # Check if message is from the managed group (or DM for testing)
    is_from_group = (message.chat_id == config.GROUP_CHAT_ID)
    is_dm = (message.chat.type == "private")
    
    if not (is_from_group or is_dm):
        return

    # Extract media metadata
    file_id = None
    file_unique_id = None
    media_type = None
    file_size = 0
    duration = None
    width = None
    height = None

    if message.video:
        media_type = "video"
        file_id = message.video.file_id
        file_unique_id = message.video.file_unique_id
        file_size = message.video.file_size
        duration = message.video.duration
        width = message.video.width
        height = message.video.height
    elif message.photo:
        media_type = "photo"
        # Get highest resolution
        photo = message.photo[-1]
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        file_size = photo.file_size
        width = photo.width
        height = photo.height
    elif message.document:
        # Check if it's a video/photo sent as document
        mime = message.document.mime_type or ""
        if mime.startswith("video/") or mime.startswith("image/"):
            media_type = "document"
            file_id = message.document.file_id
            file_unique_id = message.document.file_unique_id
            file_size = message.document.file_size
    elif message.animation:
        media_type = "animation"
        file_id = message.animation.file_id
        file_unique_id = message.animation.file_unique_id
        file_size = message.animation.file_size
        duration = message.animation.duration

    if not file_id:
        return

    async with get_session() as session:
        # Check permission (SRS §7.1: import)
        user_id = message.from_user.id
        can_import = await has_permission(session, user_id, config.OWNER_TELEGRAM_ID, Permission.IMPORT)
        
        if not can_import:
            # Silently ignore group messages, reply to DM
            if is_dm:
                await message.reply_text(MSG.UNAUTHORIZED)
            return

        # Import to DB
        media, is_new = await import_media(
            session=session,
            file_id=file_id,
            file_unique_id=file_unique_id,
            media_type=media_type,
            file_size=file_size,
            caption=message.caption,
            duration=duration,
            width=width,
            height=height,
            uploader_id=user_id,
            uploader_name=message.from_user.full_name,
            message_id=message.message_id,
            chat_id=message.chat_id
        )

        if not is_new and is_dm:
            await message.reply_text(MSG.IMPORT_ALREADY_EXISTS.format(status=media.status))
            return

        # Trigger duplicate scan (SRS §12.1)
        potentials = await scan_for_duplicates(session, media)
        if potentials:
            await create_duplicate_group(session, [media] + potentials)
            logger.info("Duplicate group created for media %d", media.id)


def register_import_handlers(application) -> None:
    """Register the import handler."""
    application.add_handler(
        MessageHandler(
            filters.VIDEO | filters.PHOTO | filters.Document.ALL | filters.ANIMATION,
            media_import_handler
        )
    )
