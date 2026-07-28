"""
app/telegram/handlers/publish_handler.py
==========================================
Handlers for publishing management.
SRS §14: Manual publishing, Order selection, Job control.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from app.database.engine import get_session
from app.services.category_service import get_all_categories
from app.publishing.queue_builder import build_queue, OrderMode
from app.database.models.publish_job import PublishJob, PublishJobStatus
from app.audit.logger import log_action, AuditAction
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import CB, publish_menu_keyboard, publish_order_keyboard, category_select_keyboard, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


@require_permission(Permission.PUBLISH)
async def show_publish_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    
    async with get_session() as session:
        # Check if there's an active job
        from sqlalchemy import select
        result = await session.execute(
            select(PublishJob).where(PublishJob.status == PublishJobStatus.RUNNING.value).limit(1)
        )
        active_job = result.scalar_one_or_none()
        
        await query.answer()
        await query.edit_message_text(
            MSG.PUBLISH_MENU,
            reply_markup=publish_menu_keyboard(has_running_job=bool(active_job))
        )


async def prompt_publish_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Choose category for publishing."""
    query = update.callback_query
    
    async with get_session() as session:
        categories = await get_all_categories(session)
        await query.answer()
        await query.edit_message_text(
            "בחר קטגוריה לפרסום:",
            reply_markup=category_select_keyboard(
                categories, 
                back_cb=CB.PUBLISH,
                select_prefix="pub_cat_sel:"
            )
        )


async def choose_publish_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Choose order after selecting category."""
    query = update.callback_query
    cat_id = query.data.split(":")[1]
    context.user_data["publish_cat_id"] = int(cat_id) if cat_id != "all" else None
    
    await query.answer()
    await query.edit_message_text(
        MSG.PUBLISH_CHOOSE_ORDER,
        reply_markup=publish_order_keyboard()
    )


async def start_manual_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Actually start the publishing process."""
    query = update.callback_query
    order_mode = query.data.split(":")[1]
    cat_id = context.user_data.get("publish_cat_id")
    user_id = update.effective_user.id
    
    async with get_session() as session:
        # 1. Create Job
        job = PublishJob(
            status=PublishJobStatus.RUNNING.value,
            category_id=cat_id,
            order_mode=order_mode,
            created_by_admin_id=user_id
        )
        session.add(job)
        await session.flush()
        
        # 2. Build Queue
        count = await build_queue(session, job.id, category_id=cat_id, order_mode=order_mode)
        
        if count == 0:
            await query.answer(MSG.PUBLISH_NO_ITEMS, show_alert=True)
            await session.delete(job)
            return
            
        await log_action(session, AuditAction.PUBLISH_JOB_STARTED, actor_telegram_id=user_id, details={"count": count})
        
        # 3. Trigger Worker
        worker = context.application.bot_data["publish_worker"]
        await worker.start_job(job.id)
        
        await query.answer(f"הפרסום החל! {count} פריטים בתור.")
        await show_publish_menu(update, context)


async def stop_publish_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(PublishJob).where(PublishJob.status == PublishJobStatus.RUNNING.value).limit(1)
        )
        job = result.scalar_one_or_none()
        
        if job:
            job.status = PublishJobStatus.STOPPED.value
            await session.flush()
            
            worker = context.application.bot_data["publish_worker"]
            await worker.stop_job(job.id)
            
            await log_action(session, AuditAction.PUBLISH_JOB_STOPPED, actor_telegram_id=user_id)
            await query.answer("הפרסום הופסק.")
            
        await show_publish_menu(update, context)


def register_publish_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(show_publish_menu, pattern=f"^{CB.PUBLISH}$"))
    application.add_handler(CallbackQueryHandler(prompt_publish_topic, pattern=f"^{CB.PUB_TOPIC}$"))
    application.add_handler(CallbackQueryHandler(choose_publish_order, pattern="^pub_cat_sel:"))
    application.add_handler(CallbackQueryHandler(start_manual_publish, pattern=f"^{CB.PUB_ORDER}"))
    application.add_handler(CallbackQueryHandler(stop_publish_job, pattern=f"^{CB.PUB_STOP}$"))
