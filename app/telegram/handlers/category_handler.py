"""
app/telegram/handlers/category_handler.py
===========================================
Handlers for category management.
SRS §11: Create, Rename, Delete, Merge, Sync.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from app.database.engine import get_session
from app.services.category_service import (
    get_all_categories, get_category_by_id, create_category, 
    rename_category, delete_category, merge_categories
)
from app.services.permission_service import has_permission, Permission, require_permission
from app.config import config
from app.telegram.keyboards import CB, categories_list_keyboard, category_actions_keyboard, confirm_keyboard, main_menu_keyboard
from app.telegram.messages import MSG

logger = logging.getLogger(__name__)


@require_permission(Permission.MANAGE_CATEGORIES)
async def list_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the list of categories."""
    query = update.callback_query
    page = int(query.data.split(":")[1]) if ":" in query.data else 0
    
    async with get_session() as session:
        categories = await get_all_categories(session)
        keyboard = categories_list_keyboard(categories, page=page)
        
        await query.answer()
        await query.edit_message_text(MSG.CATEGORIES_MENU, reply_markup=keyboard)


async def category_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display actions for a single category."""
    query = update.callback_query
    cat_id = int(query.data.split(":")[1])
    
    async with get_session() as session:
        category = await get_category_by_id(session, cat_id)
        if not category:
            await query.answer(MSG.CATEGORY_NOT_FOUND)
            return
            
        emoji = category.emoji or "📁"
        text = f"{emoji} **{category.name}**\n"
        if category.telegram_thread_id:
            text += f"🔗 מקושר ל-Topic ID: {category.telegram_thread_id}"
        else:
            text += "⚠️ לא מקושר ל-Topic"
            
        await query.answer()
        await query.edit_message_text(text, reply_markup=category_actions_keyboard(cat_id), parse_mode="Markdown")


@require_permission(Permission.MANAGE_CATEGORIES)
async def prompt_create_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask user for the new category name."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(MSG.CATEGORY_CREATE_NAME_PROMPT)
    context.user_data["awaiting_category_name"] = True


async def handle_category_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the name input for new category."""
    if not context.user_data.get("awaiting_category_name"):
        return
        
    name = update.message.text
    user_id = update.effective_user.id
    
    async with get_session() as session:
        try:
            await create_category(session, name, actor_id=user_id)
            context.user_data["awaiting_category_name"] = False
            await update.message.reply_text(
                f"✅ קטגוריה '{name}' נוצרה בהצלחה.",
                reply_markup=main_menu_keyboard()
            )
        except ValueError as e:
            await update.message.reply_text(str(e))


async def prompt_delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show confirmation for deletion."""
    query = update.callback_query
    cat_id = int(query.data.split(":")[1])
    
    async with get_session() as session:
        category = await get_category_by_id(session, cat_id)
        # Count items to be returned to queue
        from sqlalchemy import select, func
        from app.database.models.media import Media
        result = await session.execute(select(func.count()).where(Media.category_id == cat_id))
        count = result.scalar_one()
        
        text = MSG.CONFIRM_TEMPLATE.format(
            description=MSG.CONFIRM_DELETE_CATEGORY.format(count=count),
            details=f"שם הקטגוריה: {category.name}"
        )
        
        await query.answer()
        await query.edit_message_text(
            text, 
            reply_markup=confirm_keyboard(
                yes_cb=f"cat_del_confirm:{cat_id}",
                no_cb=f"cat_detail:{cat_id}"
            )
        )


async def confirm_delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    cat_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    
    async with get_session() as session:
        count = await delete_category(session, cat_id, actor_id=user_id)
        await query.answer(MSG.CATEGORY_DELETED.format(count=count), show_alert=True)
        await list_categories(update, context)


def register_category_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(list_categories, pattern=f"^{CB.TOPICS}$|^{CB.CAT_PAGE}"))
    application.add_handler(CallbackQueryHandler(category_detail, pattern="^cat_detail:"))
    application.add_handler(CallbackQueryHandler(prompt_create_category, pattern=f"^{CB.CAT_NEW}$"))
    application.add_handler(CallbackQueryHandler(prompt_delete_category, pattern=f"^{CB.CAT_DELETE}"))
    application.add_handler(CallbackQueryHandler(confirm_delete_category, pattern="^cat_del_confirm:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_name_input))
