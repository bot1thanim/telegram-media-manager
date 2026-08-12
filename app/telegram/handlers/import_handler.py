"""Live authorized media import from direct messages and configured source topics."""

from __future__ import annotations

import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.config import config
from app.database.engine import get_session
from app.database.models.topic_catalog import TopicCatalog
from app.duplicate_detector.detector import create_duplicate_group, scan_for_duplicates
from app.services.category_service import get_category_by_id
from app.services.media_service import categorize_media, import_media
from app.services.permission_service import Permission, has_permission
from app.sync.services import ensure_source_category, ingest_source_media
from app.telegram.handlers.direct_upload_handler import get_pending_upload_category_id
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


async def _source_topic_name(
    session, chat_id: int, thread_id: int
) -> str | None:
    result = await session.execute(
        select(TopicCatalog.name).where(
            TopicCatalog.chat_id == chat_id,
            TopicCatalog.thread_id == thread_id,
            TopicCatalog.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def media_import_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Import source-topic media automatically and direct-message media by permission."""
    message = update.effective_message
    sender = update.effective_user
    if message is None:
        return

    is_from_source_group = message.chat_id == config.SOURCE_GROUP_CHAT_ID
    is_direct_message = message.chat.type == "private"
    if not (is_from_source_group or is_direct_message):
        return
    # Never ingest the bot's own delivery back into the source catalog. This is
    # essential when legacy GROUP_CHAT_ID makes source and target the same chat.
    if is_from_source_group and sender is not None and sender.id == context.bot.id:
        return

    if message.video is not None:
        media_type = "video"
        source = message.video
        duration = source.duration
    elif message.photo:
        media_type = "photo"
        source = message.photo[-1]
        duration = None
    elif message.document is not None:
        media_type = "document"
        source = message.document
        duration = None
    else:
        return

    if is_from_source_group:
        thread_id = message.message_thread_id
        if thread_id is None:
            logger.info(
                "Ignoring source media outside a forum topic: chat=%d message=%d",
                message.chat_id,
                message.message_id,
            )
            return
        async with get_session() as session:
            topic_name = await _source_topic_name(session, message.chat_id, thread_id)
            if topic_name is None:
                logger.warning(
                    "Ignoring source media before its topic was catalogued: chat=%d thread=%d message=%d",
                    message.chat_id,
                    thread_id,
                    message.message_id,
                )
                return
            category, _created = await ensure_source_category(
                session,
                source_group_id=message.chat_id,
                source_thread_id=thread_id,
                topic_name=topic_name,
                actor_id=sender.id if sender else None,
            )
            result = await ingest_source_media(
                session,
                file_id=source.file_id,
                file_unique_id=source.file_unique_id,
                media_type=media_type,
                file_size=source.file_size,
                caption=message.caption,
                duration=duration,
                uploader_id=sender.id if sender else None,
                source_group_id=message.chat_id,
                source_thread_id=thread_id,
                source_message_id=message.message_id,
                category_id=category.id,
                actor_id=sender.id if sender else None,
            )
            if not result.is_new:
                logger.info(
                    "Skipped duplicate source media: chat=%d message=%d reason=%s",
                    message.chat_id,
                    message.message_id,
                    result.duplicate_reason,
                )
        return

    if sender is None:
        return
    async with get_session() as session:
        can_import = await has_permission(
            session,
            sender.id,
            config.OWNER_TELEGRAM_ID,
            Permission.IMPORT,
        )
        if not can_import:
            await message.reply_text(MSG.UNAUTHORIZED)
            return

        selected_category_id = get_pending_upload_category_id(context)
        selected_category = (
            await get_category_by_id(session, selected_category_id)
            if selected_category_id is not None
            else None
        )
        if selected_category_id is not None and selected_category is None:
            context.user_data.pop("direct_upload_category_id", None)
            context.user_data.pop("direct_upload_started_at", None)
            await message.reply_text(MSG.DIRECT_UPLOAD_CATEGORY_MISSING)
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
            chat_id=message.chat_id,
        )
        if not is_new:
            reply = (
                MSG.DIRECT_UPLOAD_DUPLICATE.format(status=media.status)
                if selected_category is not None
                else MSG.IMPORT_ALREADY_EXISTS.format(status=media.status)
            )
            await message.reply_text(reply)
            return

        if selected_category is not None:
            await categorize_media(
                session,
                media.id,
                selected_category.id,
                actor_id=sender.id,
            )

        potentials = await scan_for_duplicates(session, media)
        if potentials:
            await create_duplicate_group(session, [media, *potentials])
            logger.info("Duplicate group created for media %d", media.id)

        if selected_category is not None:
            await message.reply_text(
                MSG.DIRECT_UPLOAD_SAVED.format(category_name=selected_category.name)
            )


def register_import_handlers(application) -> None:
    """Register source and direct media routes for video, photo, and document."""
    application.add_handler(
        MessageHandler(filters.VIDEO | filters.PHOTO | filters.Document.ALL, media_import_handler)
    )
