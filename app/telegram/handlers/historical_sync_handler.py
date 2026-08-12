"""Owner-only Telegram entry point for the local historical synchronization workflow."""

from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.services.permission_service import owner_only
from app.telegram.messages import MSG


@owner_only
async def show_historical_sync_guidance(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Explain the secure one-time import route without collecting account secrets."""
    del context
    message = update.effective_message
    if message is not None:
        await message.reply_text(MSG.TOPIC_SYNC_HISTORICAL_GUIDANCE)


def register_historical_sync_handlers(application) -> None:
    """Register the owner-only /sync_topics command."""
    application.add_handler(CommandHandler("sync_topics", show_historical_sync_guidance))
