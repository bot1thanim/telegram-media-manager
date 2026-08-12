"""
Application entry point for the Telegram Media Manager.

The process owns one asynchronous SQLAlchemy engine, one Telegram application,
one APScheduler instance, and one aiohttp server.  Database schema changes are
applied exclusively by Alembic in the Render pre-deploy command.
"""

import asyncio
import logging
import os
import signal
import sys

from aiohttp import web
from telegram.error import TelegramError
from telegram.ext import Application, MessageHandler, filters

from app.config import config
from app.database.engine import close_engine, get_session, init_engine
from app.database.models import SETTING_DEFAULTS
from app.database.models.setting import Setting
from app.publishing.worker import PublishWorker
from app.scheduler.manager import init_scheduler, shutdown_scheduler
from app.telegram.handlers.admin_handler import (
    handle_add_admin_message,
    register_admin_handlers,
)
from app.telegram.handlers.backup_handler import register_backup_handlers
from app.telegram.handlers.category_handler import register_category_handlers
from app.telegram.handlers.dashboard_handler import register_dashboard_handlers
from app.telegram.handlers.direct_upload_handler import register_direct_upload_handlers
from app.telegram.handlers.duplicate_handler import register_duplicate_handlers
from app.telegram.handlers.historical_sync_handler import (
    register_historical_sync_handlers,
)
from app.telegram.handlers.import_handler import register_import_handlers
from app.telegram.handlers.main_menu import register_main_menu_handlers
from app.telegram.handlers.publish_handler import register_publish_handlers
from app.telegram.handlers.recycle_bin_handler import register_recycle_bin_handlers
from app.telegram.handlers.sorting_handler import register_sorting_handlers
from app.telegram.handlers.topic_sync_handler import register_topic_sync_handlers
from app.telegram.webhook_server import build_aiohttp_app

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
# HTTP request URLs to Telegram embed the bot token. Keep transport logs above
# INFO even when application logging is configured at a verbose level.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def seed_default_settings() -> None:
    """Insert missing defaults without overwriting administrator-managed values."""
    from sqlalchemy import select

    async with get_session() as session:
        for key, value in SETTING_DEFAULTS.items():
            result = await session.execute(select(Setting).where(Setting.key == key))
            if result.scalar_one_or_none() is None:
                session.add(Setting(key=key, value=value))


async def build_application() -> Application:
    """Create the PTB application and register every supported handler."""
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    register_main_menu_handlers(application)
    register_direct_upload_handlers(application)
    register_historical_sync_handlers(application)
    register_topic_sync_handlers(application)
    register_import_handlers(application)
    register_duplicate_handlers(application)
    register_sorting_handlers(application)
    register_category_handlers(application)
    register_publish_handlers(application)
    register_recycle_bin_handlers(application)
    register_backup_handlers(application)
    register_dashboard_handlers(application)
    register_admin_handlers(application)
    # This handler must be placed after other message handlers to avoid conflicts
    application.add_handler(
        MessageHandler(
            filters.FORWARDED & filters.User(config.OWNER_TELEGRAM_ID),
            handle_add_admin_message,
        )
    )
    return application


async def set_webhook_with_retry(application: Application) -> None:
    """Register the webhook while tolerating short-lived Telegram API outages."""
    retry_delays = (1, 3, 9)
    for attempt, delay in enumerate(retry_delays, start=1):
        try:
            await application.bot.set_webhook(
                url=config.webhook_url,
                secret_token=config.WEBHOOK_SECRET_TOKEN,
                allowed_updates=["message", "callback_query", "edited_message"],
                drop_pending_updates=False,
            )
            logger.info("Telegram webhook registered at %s", config.webhook_url)
            return
        except TelegramError:
            if attempt == len(retry_delays):
                logger.exception(
                    "Unable to register Telegram webhook after %d attempts", attempt
                )
                raise
            logger.warning(
                "Webhook registration attempt %d/%d failed; retrying in %d seconds",
                attempt,
                len(retry_delays),
                delay,
            )
            await asyncio.sleep(delay)


def install_shutdown_signals(stop_event: asyncio.Event) -> None:
    """Request a graceful shutdown when Render sends SIGTERM or SIGINT."""
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Signal handlers are unavailable on some local development platforms.
            pass


async def main() -> None:
    """Start all components and keep the process alive until graceful shutdown."""
    init_engine(config.DATABASE_URL)
    application = await build_application()
    worker: PublishWorker | None = None
    runner: web.AppRunner | None = None
    application_initialized = False
    application_started = False

    try:
        # PTB must be initialized before processing Telegram updates.
        await application.initialize()
        application_initialized = True
        await seed_default_settings()

        worker = PublishWorker(application)
        application.bot_data["publish_worker"] = worker
        init_scheduler(application, worker)

        await application.start()
        application_started = True

        web_app = build_aiohttp_app(
            ptb_application=application,
            webhook_secret_token=config.WEBHOOK_SECRET_TOKEN,
            webhook_path=config.webhook_path,
        )
        runner = web.AppRunner(web_app)
        await runner.setup()
        port = int(os.environ.get("PORT", "10000"))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("HTTP server listening on 0.0.0.0:%d", port)

        # Register only after the HTTP listener is ready to accept Telegram updates.
        await set_webhook_with_retry(application)

        stop_event = asyncio.Event()
        install_shutdown_signals(stop_event)
        await stop_event.wait()
    finally:
        if runner is not None:
            await runner.cleanup()
        await shutdown_scheduler()
        if worker is not None:
            await worker.shutdown()
        if application_started:
            await application.stop()
        if application_initialized:
            await application.shutdown()
        await close_engine()
        logger.info("Application shutdown completed")


if __name__ == "__main__":
    asyncio.run(main())
