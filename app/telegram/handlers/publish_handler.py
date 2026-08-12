"""Secure manual and one-off scheduled publishing flows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.audit.logger import AuditAction, log_action
from app.database.engine import get_session
from app.database.models.publish_job import PublishJob, PublishJobStatus
from app.publishing.queue_builder import OrderMode, build_queue
from app.scheduler.manager import schedule_publish_job
from app.sync.topic_broadcaster import (
    BroadcastAlreadyRunningError,
    broadcast_all_categories,
)
from app.services.category_service import get_all_categories
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import (
    CB,
    category_select_keyboard,
    publish_menu_keyboard,
    publish_order_keyboard,
    publish_schedule_scope_keyboard,
)
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)
_ACTIVE_JOB_STATUSES = (
    PublishJobStatus.QUEUED.value,
    PublishJobStatus.RUNNING.value,
    PublishJobStatus.PAUSED.value,
)
_ORDER_MODES = {
    OrderMode.RANDOM,
    OrderMode.OLDEST_FIRST,
    OrderMode.NEWEST_FIRST,
    OrderMode.SHORTEST_FIRST,
    OrderMode.LONGEST_FIRST,
}
_PUBLISH_LOCK_KEY = 2_918_474
_SCHEDULE_TIME_FORMAT = "%Y-%m-%d %H:%M"


async def _lock_publishing(session) -> None:
    """Serialize active-job creation across Render processes on PostgreSQL."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _PUBLISH_LOCK_KEY},
        )


async def _has_active_job(session) -> bool:
    result = await session.execute(
        select(PublishJob.id)
        .where(PublishJob.status.in_(_ACTIVE_JOB_STATUSES))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _render_publish_menu(query) -> None:
    async with get_session() as session:
        has_running_job = await _has_active_job(session)
    await query.edit_message_text(
        MSG.PUBLISH_MENU,
        reply_markup=publish_menu_keyboard(has_running_job=has_running_job),
    )


async def _show_category_picker(
    update: Update,
    *,
    select_prefix: str,
    back_callback: str,
    prompt: str,
) -> None:
    query = update.callback_query
    async with get_session() as session:
        categories = await get_all_categories(session)
    if not categories:
        await query.answer(
            "אין עדיין נושאים. צור נושא לפני פרסום לפי נושא.", show_alert=True
        )
        return
    await query.answer()
    await query.edit_message_text(
        prompt,
        reply_markup=category_select_keyboard(
            categories,
            back_cb=back_callback,
            select_prefix=select_prefix,
            include_create=False,
        ),
    )


async def _create_publish_job(
    *,
    scope_category_id: int | None,
    order_mode: str,
    user_id: int,
    is_scheduled: bool,
    scheduled_at: datetime | None,
) -> tuple[int | None, int]:
    """Create one queue snapshot, returning its job ID and item count.

    PostgreSQL advisory locking prevents two duplicated Telegram callbacks from
    producing concurrent active jobs. The lock is a no-op under SQLite tests.
    """
    try:
        async with get_session() as session:
            await _lock_publishing(session)
            if await _has_active_job(session):
                return None, 0

            job = PublishJob(
                status=(
                    PublishJobStatus.QUEUED.value
                    if is_scheduled
                    else PublishJobStatus.RUNNING.value
                ),
                scope="all" if scope_category_id is None else "category",
                scope_category_id=scope_category_id,
                order_mode=order_mode,
                created_by_user_id=user_id,
                is_scheduled=is_scheduled,
                scheduled_at=scheduled_at,
            )
            session.add(job)
            await session.flush()

            count = await build_queue(
                session,
                job.id,
                category_id=scope_category_id,
                order_mode=order_mode,
            )
            if count == 0:
                await session.delete(job)
                return 0, 0

            await log_action(
                session,
                AuditAction.PUBLISH_JOB_STARTED,
                actor_telegram_id=user_id,
                details={
                    "job_id": job.id,
                    "count": count,
                    "scheduled": is_scheduled,
                    "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                },
            )
            return job.id, count
    except IntegrityError:
        logger.warning("Concurrent publish queue creation was rejected")
        return None, 0


@require_permission(Permission.PUBLISH)
async def show_publish_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the supported publishing actions."""
    del context
    query = update.callback_query
    await query.answer()
    await _render_publish_menu(query)


@require_permission(Permission.PUBLISH)
async def prompt_publish_topic(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Choose a category for immediate publication."""
    del context
    await _show_category_picker(
        update,
        select_prefix=CB.PUB_CAT_SELECT,
        back_callback=CB.PUBLISH,
        prompt="בחר נושא לפרסום מיידי:",
    )


@require_permission(Permission.PUBLISH)
async def prompt_publish_all(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Choose ordering for immediate publication of every ready item."""
    context.user_data["publish_scope_category_id"] = None
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        MSG.PUBLISH_CHOOSE_ORDER,
        reply_markup=publish_order_keyboard(),
    )


@require_permission(Permission.PUBLISH)
async def choose_publish_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Persist a validated manual scope, then ask for an ordering mode."""
    query = update.callback_query
    raw_category_id = query.data.removeprefix(CB.PUB_CAT_SELECT)
    if not raw_category_id.isdigit():
        await query.answer("בחירת נושא לא תקינה.", show_alert=True)
        return
    context.user_data["publish_scope_category_id"] = int(raw_category_id)
    await query.answer()
    await query.edit_message_text(
        MSG.PUBLISH_CHOOSE_ORDER,
        reply_markup=publish_order_keyboard(),
    )


@require_permission(Permission.PUBLISH)
async def start_manual_publish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Create a durable queue and start the in-process worker after commit."""
    query = update.callback_query
    order_mode = query.data.removeprefix(CB.PUB_ORDER)
    if order_mode not in _ORDER_MODES:
        await query.answer("סדר פרסום לא תקין.", show_alert=True)
        return

    job_id, count = await _create_publish_job(
        scope_category_id=context.user_data.get("publish_scope_category_id"),
        order_mode=order_mode,
        user_id=update.effective_user.id,
        is_scheduled=False,
        scheduled_at=None,
    )
    context.user_data.pop("publish_scope_category_id", None)

    if job_id is None:
        await query.answer("כבר קיימת עבודת פרסום פעילה.", show_alert=True)
        return
    if job_id == 0:
        await query.answer(MSG.PUBLISH_NO_ITEMS, show_alert=True)
        return

    worker = context.application.bot_data["publish_worker"]
    await worker.start_job(job_id)
    await query.answer(f"הפרסום החל: {count} פריטים בתור.")
    await _render_publish_menu(query)


@require_permission(Permission.PUBLISH)
async def prompt_schedule_publish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Start the one-off scheduling flow."""
    del context
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "בחר היקף עבור הפרסום המתוזמן:",
        reply_markup=publish_schedule_scope_keyboard(),
    )


@require_permission(Permission.PUBLISH)
async def prompt_schedule_topic(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Choose a category for a one-off scheduled publish."""
    del context
    await _show_category_picker(
        update,
        select_prefix=CB.PUB_SCHED_CAT_SELECT,
        back_callback=CB.PUB_SCHEDULE,
        prompt="בחר נושא לתזמון:",
    )


@require_permission(Permission.PUBLISH)
async def prompt_schedule_all(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Choose queue order for a whole-library scheduled publish."""
    context.user_data["scheduled_publish_scope_category_id"] = None
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        MSG.PUBLISH_CHOOSE_ORDER,
        reply_markup=publish_order_keyboard(
            callback_prefix=CB.PUB_SCHED_ORDER,
            back_callback=CB.PUB_SCHEDULE,
        ),
    )


@require_permission(Permission.PUBLISH)
async def choose_schedule_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Persist a category scope for a one-off scheduled publish."""
    query = update.callback_query
    raw_category_id = query.data.removeprefix(CB.PUB_SCHED_CAT_SELECT)
    if not raw_category_id.isdigit():
        await query.answer("בחירת נושא לא תקינה.", show_alert=True)
        return
    context.user_data["scheduled_publish_scope_category_id"] = int(raw_category_id)
    await query.answer()
    await query.edit_message_text(
        MSG.PUBLISH_CHOOSE_ORDER,
        reply_markup=publish_order_keyboard(
            callback_prefix=CB.PUB_SCHED_ORDER,
            back_callback=CB.PUB_SCHEDULE,
        ),
    )


@require_permission(Permission.PUBLISH)
async def prompt_schedule_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Collect a UTC time only after validated schedule scope and order selection."""
    query = update.callback_query
    order_mode = query.data.removeprefix(CB.PUB_SCHED_ORDER)
    if order_mode not in _ORDER_MODES:
        await query.answer("סדר פרסום לא תקין.", show_alert=True)
        return
    context.user_data["scheduled_publish_order_mode"] = order_mode
    context.user_data["awaiting_publish_schedule_time"] = True
    await query.answer()
    await query.edit_message_text(
        "שלח את זמן הפרסום בפורמט `YYYY-MM-DD HH:MM` לפי UTC.\n"
        "לדוגמה: `2026-08-01 14:30`.",
        parse_mode="Markdown",
    )


async def handle_schedule_time_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Consume a pending schedule-time message; return True only when consumed."""
    if not context.user_data.get("awaiting_publish_schedule_time"):
        return False

    message = update.effective_message
    raw_value = (message.text or "").strip()
    try:
        run_at = datetime.strptime(raw_value, _SCHEDULE_TIME_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        await message.reply_text(
            "פורמט זמן לא תקין. שלח `YYYY-MM-DD HH:MM` לפי UTC, למשל `2026-08-01 14:30`.",
            parse_mode="Markdown",
        )
        return True

    if run_at <= datetime.now(timezone.utc):
        await message.reply_text("יש לבחור זמן עתידי לפי UTC.")
        return True

    order_mode = context.user_data.get("scheduled_publish_order_mode")
    if order_mode not in _ORDER_MODES:
        context.user_data.pop("awaiting_publish_schedule_time", None)
        await message.reply_text("תהליך התזמון פג. פתח אותו מחדש מתפריט הפרסום.")
        return True

    job_id, count = await _create_publish_job(
        scope_category_id=context.user_data.get("scheduled_publish_scope_category_id"),
        order_mode=order_mode,
        user_id=update.effective_user.id,
        is_scheduled=True,
        scheduled_at=run_at,
    )
    for key in (
        "awaiting_publish_schedule_time",
        "scheduled_publish_order_mode",
        "scheduled_publish_scope_category_id",
    ):
        context.user_data.pop(key, None)

    if job_id is None:
        await message.reply_text("כבר קיימת עבודת פרסום פעילה.")
        return True
    if job_id == 0:
        await message.reply_text(MSG.PUBLISH_NO_ITEMS)
        return True

    try:
        await schedule_publish_job(job_id, run_at=run_at)
    except Exception:
        logger.exception("Unable to persist APScheduler job %d", job_id)
        async with get_session() as session:
            job = await session.get(PublishJob, job_id, with_for_update=True)
            if job is not None:
                job.status = PublishJobStatus.FAILED.value
        await message.reply_text("שמירת התזמון נכשלה. העבודה סומנה ככשלה ולא תפורסם.")
        return True

    await message.reply_text(
        f"הפרסום תוזמן ל־{run_at.strftime(_SCHEDULE_TIME_FORMAT)} UTC עבור {count} פריטים."
    )
    return True


async def _run_all_categories_broadcast(
    *, chat_id: int, requested_by_user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Run the long publication outside the callback deadline and report its result."""
    try:
        report = await broadcast_all_categories(
            context.bot, requested_by_user_id=requested_by_user_id
        )
    except BroadcastAlreadyRunningError:
        await context.bot.send_message(
            chat_id=chat_id, text=MSG.TOPIC_BROADCAST_ALREADY_RUNNING
        )
    except Exception:
        logger.exception("All-categories broadcast failed before a report was delivered")
        await context.bot.send_message(
            chat_id=chat_id,
            text="השליחה לכל הקטגוריות נכשלה לפני סיום. הפרטים נרשמו בדוח הסנכרון.",
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text=report.to_telegram_text())


@require_permission(Permission.PUBLISH)
async def start_all_categories_broadcast(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Start name-matched category broadcast without blocking Telegram's callback."""
    query = update.callback_query
    message = query.message
    user = update.effective_user
    if message is None or user is None:
        await query.answer(MSG.ERROR_GENERIC, show_alert=True)
        return
    await query.answer("השליחה התחילה.")
    await query.edit_message_text(MSG.TOPIC_BROADCAST_STARTED)
    context.application.create_task(
        _run_all_categories_broadcast(
            chat_id=message.chat_id,
            requested_by_user_id=user.id,
            context=context,
        ),
        update=update,
        name=f"topic-broadcast-{user.id}",
    )


@require_permission(Permission.PUBLISH)
async def stop_publish_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop the sole active job after persisting terminal status first."""
    query = update.callback_query
    job_id: int | None = None
    async with get_session() as session:
        await _lock_publishing(session)
        result = await session.execute(
            select(PublishJob)
            .where(PublishJob.status.in_(_ACTIVE_JOB_STATUSES))
            .order_by(PublishJob.created_at.asc())
            .limit(1)
            .with_for_update()
        )
        job = result.scalar_one_or_none()
        if job is not None:
            job.status = PublishJobStatus.STOPPED.value
            job.completed_at = datetime.now(timezone.utc)
            job_id = job.id
            await log_action(
                session,
                AuditAction.PUBLISH_JOB_STOPPED,
                actor_telegram_id=update.effective_user.id,
                details={"job_id": job.id},
            )

    if job_id is None:
        await query.answer("אין עבודת פרסום פעילה.", show_alert=True)
        return

    worker = context.application.bot_data["publish_worker"]
    await worker.stop_job(job_id)
    await query.answer("הפרסום הופסק.")
    await _render_publish_menu(query)


def register_publish_handlers(application) -> None:
    """Register exact callback patterns so malformed data cannot reach handlers."""
    application.add_handler(
        CallbackQueryHandler(show_publish_menu, pattern=f"^{CB.PUBLISH}$")
    )
    application.add_handler(
        CallbackQueryHandler(prompt_publish_topic, pattern=f"^{CB.PUB_TOPIC}$")
    )
    application.add_handler(
        CallbackQueryHandler(prompt_publish_all, pattern=f"^{CB.PUB_ALL}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            start_all_categories_broadcast, pattern=f"^{CB.PUB_ALL_CATEGORIES}$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            choose_publish_category, pattern=f"^{CB.PUB_CAT_SELECT}\\d+$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            start_manual_publish,
            pattern=(
                f"^{CB.PUB_ORDER}(?:random|oldest_first|newest_first|shortest_first|longest_first)$"
            ),
        )
    )
    application.add_handler(
        CallbackQueryHandler(prompt_schedule_publish, pattern=f"^{CB.PUB_SCHEDULE}$")
    )
    application.add_handler(
        CallbackQueryHandler(prompt_schedule_topic, pattern=f"^{CB.PUB_SCHED_TOPIC}$")
    )
    application.add_handler(
        CallbackQueryHandler(prompt_schedule_all, pattern=f"^{CB.PUB_SCHED_ALL}$")
    )
    application.add_handler(
        CallbackQueryHandler(
            choose_schedule_category, pattern=f"^{CB.PUB_SCHED_CAT_SELECT}\\d+$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            prompt_schedule_time,
            pattern=(
                f"^{CB.PUB_SCHED_ORDER}(?:random|oldest_first|newest_first|shortest_first|longest_first)$"
            ),
        )
    )
    application.add_handler(
        CallbackQueryHandler(stop_publish_job, pattern=f"^{CB.PUB_STOP}$")
    )
