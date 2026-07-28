"""
app/main.py
============
Application entry point.
- Loads configuration
- Initialises database engine
- Registers all Telegram handlers
- Initialises Scheduler and Publish Worker
- Starts aiohttp web server
"""

import asyncio
import logging
import os
import sys

from aiohttp import web
from telegram.ext import Application

from app.config import config
from app.database.engine import init_engine, create_all_tables, close_engine, get_session
from app.database.models import SETTING_DEFAULTS
from app.database.models.setting import Setting
from app.telegram.webhook_server import build_aiohttp_app
from app.scheduler.manager import init_scheduler
from app.publishing.worker import PublishWorker

# Handlers
from app.telegram.handlers.main_menu import register_main_menu_handlers
from app.telegram.handlers.import_handler import register_import_handlers
from app.telegram.handlers.sorting_handler import register_sorting_handlers
from app.telegram.handlers.category_handler import register_category_handlers
from app.telegram.handlers.publish_handler import register_publish_handlers
from app.telegram.handlers.recycle_bin_handler import register_recycle_bin_handlers
from app.telegram.handlers.backup_handler import register_backup_handlers
from app.telegram.handlers.dashboard_handler import register_dashboard_handlers
from app.telegram.handlers.admin_handler import register_admin_handlers

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def seed_default_settings(session) -> None:
    from sqlalchemy import select
    for key, value in SETTING_DEFAULTS.items():
        result = await session.execute(select(Setting).where(Setting.key == key))
        if not result.scalar_one_or_none():
            session.add(Setting(key=key, value=value))
    await session.flush()


async def build_application() -> Application:
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Register all handlers
    register_main_menu_handlers(application)
    register_import_handlers(application)
    register_sorting_handlers(application)
    register_category_handlers(application)
    register_publish_handlers(application)
    register_recycle_bin_handlers(application)
    register_backup_handlers(application)
    register_dashboard_handlers(application)
    register_admin_handlers(application)
    
    return application


async def main() -> None:
    init_engine(config.DATABASE_URL)
    await create_all_tables()
    
    async with get_session() as session:
        await seed_default_settings(session)
        
    application = await build_application()
    
    # Init worker and scheduler
    worker = PublishWorker(application)
    application.bot_data["publish_worker"] = worker
    init_scheduler(application)
    
    # Webhook
    await application.bot.set_webhook(
        url=config.webhook_url,
        secret_token=config.WEBHOOK_SECRET_TOKEN,
        allowed_updates=["message", "callback_query", "edited_message"]
    )
    
    web_app = build_aiohttp_app(
        ptb_application=application,
        webhook_secret_token=config.WEBHOOK_SECRET_TOKEN,
        webhook_path=config.webhook_path,
    )

    async def on_startup(app: web.Application) -> None:
        await application.initialize()
        await application.start()

    async def on_shutdown(app: web.Application) -> None:
        await application.stop()
        await application.shutdown()
        await close_engine()

    web_app.on_startup.append(on_startup)
    web_app.on_shutdown.append(on_shutdown)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
