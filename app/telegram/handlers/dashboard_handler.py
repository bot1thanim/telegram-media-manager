"""Permission-protected Telegram dashboard and audit-log handlers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.database.engine import get_session
from app.database.models.audit_log import AuditLog
from app.database.models.category import Category
from app.database.models.media import Media, MediaStatus
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import CB, dashboard_keyboard, main_menu_keyboard
from app.telegram.messages import MSG


@require_permission(Permission.VIEW_DASHBOARD)
async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display stable, schema-aligned aggregate statistics."""
    query = update.callback_query
    async with get_session() as session:
        total_media = await session.scalar(select(func.count()).select_from(Media))
        waiting_sort = await session.scalar(
            select(func.count())
            .select_from(Media)
            .where(Media.status == MediaStatus.WAITING_CATEGORIZATION.value)
        )
        ready_items = await session.scalar(
            select(func.count())
            .select_from(Media)
            .where(Media.status == MediaStatus.READY_TO_PUBLISH.value)
        )
        categories_count = await session.scalar(
            select(func.count()).select_from(Category)
        )

    text = (
        f"{MSG.DASHBOARD_HEADER.format(datetime=datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC'))}\n\n"
        "📊 **סטטיסטיקה כללית:**\n"
        f'• סה"כ מדיה במערכת: {total_media or 0}\n'
        f"• פריטים הממתינים למיון: {waiting_sort or 0}\n"
        f"• פריטים מוכנים לפרסום: {ready_items or 0}\n"
        f"• מספר קטגוריות: {categories_count or 0}\n"
    )
    await query.answer()
    await query.edit_message_text(
        text, reply_markup=dashboard_keyboard(), parse_mode="Markdown"
    )


@require_permission(Permission.VIEW_DASHBOARD)
async def show_audit_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the latest audit events only to users with dashboard access."""
    query = update.callback_query
    async with get_session() as session:
        logs = list(
            (
                await session.execute(
                    select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)
                )
            ).scalars()
        )

    lines = ["📜 **10 פעולות אחרונות:**", ""]
    lines.extend(
        f'• `{log.created_at.astimezone(timezone.utc).strftime("%H:%M UTC")}`: {log.action} (ע"י {log.actor_telegram_id})'
        for log in logs
    )
    await query.answer()
    await query.edit_message_text(
        "\n".join(lines), reply_markup=main_menu_keyboard(), parse_mode="Markdown"
    )


def register_dashboard_handlers(application) -> None:
    application.add_handler(
        CallbackQueryHandler(show_dashboard, pattern=f"^{CB.DASHBOARD}$")
    )
    application.add_handler(
        CallbackQueryHandler(show_audit_log, pattern=f"^{CB.DASH_LOG}$")
    )
