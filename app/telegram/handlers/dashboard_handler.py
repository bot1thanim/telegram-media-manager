"""
app/telegram/handlers/dashboard_handler.py
============================================
Handlers for the dashboard.
SRS §18: Statistics, Audit Log.
"""

import logging
from datetime import datetime
from sqlalchemy import select, func
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from app.database.engine import get_session
from app.database.models.media import Media, MediaStatus
from app.database.models.category import Category
from app.database.models.audit_log import AuditLog
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import CB, dashboard_keyboard, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


@require_permission(Permission.VIEW_DASHBOARD)
async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    
    async with get_session() as session:
        # Statistics
        total_media = await session.execute(select(func.count()).select_from(Media))
        pending_sort = await session.execute(select(func.count()).select_from(Media).where(Media.status == MediaStatus.PENDING_SORT.value))
        ready_items = await session.execute(select(func.count()).select_from(Media).where(Media.status == MediaStatus.READY.value))
        categories_count = await session.execute(select(func.count()).select_from(Category))
        
        text = (
            f"{MSG.DASHBOARD_HEADER.format(datetime=datetime.now().strftime('%d/%m/%Y %H:%M'))}\n\n"
            f"📊 **סטטיסטיקה כללית:**\n"
            f"• סה\"כ מדיה במערכת: {total_media.scalar_one()}\n"
            f"• פריטים הממתינים למיון: {pending_sort.scalar_one()}\n"
            f"• פריטים מוכנים לפרסום: {ready_items.scalar_one()}\n"
            f"• מספר קטגוריות: {categories_count.scalar_one()}\n"
        )
        
        await query.answer()
        await query.edit_message_text(text, reply_markup=dashboard_keyboard(), parse_mode="Markdown")


async def show_audit_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    
    async with get_session() as session:
        result = await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)
        )
        logs = result.scalars().all()
        
        text = "📜 **10 פעולות אחרונות:**\n\n"
        for log in logs:
            text += f"• `{log.created_at.strftime('%H:%M')}`: {log.action} (ע\"י {log.actor_telegram_id})\n"
            
        await query.answer()
        await query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


def register_dashboard_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(show_dashboard, pattern=f"^{CB.DASHBOARD}$"))
    application.add_handler(CallbackQueryHandler(show_audit_log, pattern=f"^{CB.DASH_LOG}$"))
