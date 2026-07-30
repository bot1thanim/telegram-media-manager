"""Authorized import of supported Telegram videos and photos."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.config import config
from app.database.engine import get_session
from app.duplicate_detector.detector import create_duplicate_group, scan_for_duplicates
from app.services.media_service import import_media
from app.services.permission_service import Permission, has_permission
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


async def media_import_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Import an authorized video or photo from the managed group or a direct message."""
    del context
    message = update.effective_message
    sender = update.effective_user
    if message is None or sender is None:
        return

    is_from_group = message.chat_id == config.GROUP_CHAT_ID
    is_direct_message = message.chat.type == "private"
    if not (is_from_group or is_direct_message):
        return

    if message.video is not None:
        media_type = "video"
        source = message.video
        duration = source.duration
    elif message.photo:
        media_type = "photo"
        source = message.photo[-1]
        duration = None
    else:
        return

    async with get_session() as session:
        can_import = await has_permission(
            session,
            sender.id,
            config.OWNER_TELEGRAM_ID,
            Permission.IMPORT,
        )
        if not can_import:
            if is_direct_message:
                await message.reply_text(MSG.UNAUTHORIZED)
            return

        media, is_new = await import_media(
            session=session,
            file_id=source.file_id,
            file_unique_id=source.file_unique_id,
            media_type=media_type,
            file_size=source.file_size or 0,
            caption=message.caption,
            duration=duration,
            uploader_id=sender.id,
            message_id=message.message_id,
        )
        if not is_new:
            if is_direct_message:
                await message.reply_text(
                    MSG.IMPORT_ALREADY_EXISTS.format(status=media.status)
                )
            return

        potentials = await scan_for_duplicates(session, media)
        if potentials:
            await create_duplicate_group(session, [media, *potentials])
            logger.info("Duplicate group created for media %d", media.id)


def register_import_handlers(application) -> None:
    """Register the video/photo import route only; unsupported payloads are ignored."""
    application.add_handler(
        MessageHandler(filters.VIDEO | filters.PHOTO, media_import_handler)
    )
