"""
app/telegram/handlers/admin_handler.py
========================================
Handlers for admin management.
SRS §20: Add/Remove admins, Permissions.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from app.database.engine import get_session
from app.database.models.admin import Admin
from app.services.permission_service import Permission, owner_only
from app.config import config
from app.telegram.keyboards import CB, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


@owner_only
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Admin))
        admins = result.scalars().all()
        
        text = MSG.ADMINS_MENU + "\n\n"
        for admin in admins:
            text += f"• {admin.display_name or 'Admin'} (`{admin.telegram_user_id}`) - {admin.role}\n"
            
        await query.answer()
        await query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


def register_admin_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(list_admins, pattern=f"^{CB.ADMINS}$"))
