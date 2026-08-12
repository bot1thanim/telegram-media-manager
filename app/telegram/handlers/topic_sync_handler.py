"""Live forum-topic catalog synchronization from Telegram webhook updates."""

from __future__ import annotations

import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.config import config
from app.database.engine import get_session
from app.database.models.topic_catalog import TopicCatalog
from app.sync.services import ensure_source_category, upsert_topic

logger = logging.getLogger(__name__)

_TOPIC_STATUS_FILTER = (
    filters.StatusUpdate.FORUM_TOPIC_CREATED
    | filters.StatusUpdate.FORUM_TOPIC_EDITED
    | filters.StatusUpdate.FORUM_TOPIC_CLOSED
    | filters.StatusUpdate.FORUM_TOPIC_REOPENED
)


async def forum_topic_catalog_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Persist topic lifecycle updates for the configured source and target chats."""
    del context
    message = update.effective_message
    if message is None or message.chat_id not in {
        config.SOURCE_GROUP_CHAT_ID,
        config.TARGET_GROUP_CHAT_ID,
    }:
        return
    thread_id = message.message_thread_id
    if thread_id is None:
        return

    created = message.forum_topic_created
    edited = message.forum_topic_edited
    is_closed_event = message.forum_topic_closed is not None
    is_reopened_event = message.forum_topic_reopened is not None

    async with get_session() as session:
        current = (
            await session.execute(
                select(TopicCatalog)
                .where(
                    TopicCatalog.chat_id == message.chat_id,
                    TopicCatalog.thread_id == thread_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

        if created is not None:
            topic = await upsert_topic(
                session,
                chat_id=message.chat_id,
                thread_id=thread_id,
                name=created.name,
                icon_color=created.icon_color,
            )
            if message.chat_id == config.SOURCE_GROUP_CHAT_ID:
                await ensure_source_category(
                    session,
                    source_group_id=message.chat_id,
                    source_thread_id=thread_id,
                    topic_name=topic.name,
                )
            return

        if edited is not None:
            if current is None:
                logger.warning(
                    "Received forum topic edit without a known topic: chat=%d thread=%d",
                    message.chat_id,
                    thread_id,
                )
                return
            topic_name = edited.name or current.name
            await upsert_topic(
                session,
                chat_id=message.chat_id,
                thread_id=thread_id,
                name=topic_name,
                icon_color=current.icon_color,
                is_closed=current.is_closed,
                is_deleted=current.is_deleted,
            )
            return

        if current is None:
            logger.warning(
                "Received forum topic state update without a known topic: chat=%d thread=%d",
                message.chat_id,
                thread_id,
            )
            return
        if is_closed_event:
            current.is_closed = True
        elif is_reopened_event:
            current.is_closed = False


def register_topic_sync_handlers(application) -> None:
    """Register narrow service-message filters before the media import handler."""
    application.add_handler(MessageHandler(_TOPIC_STATUS_FILTER, forum_topic_catalog_handler))
