"""Read-only review queue for duplicate groups created during media import."""

from __future__ import annotations

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.database.engine import get_session
from app.database.models.duplicate_group import (
    DuplicateGroup,
    DuplicateGroupStatus,
    duplicate_group_members,
)
from app.services.permission_service import Permission, require_permission
from app.telegram.keyboards import CB, main_menu_keyboard


@require_permission(Permission.CATEGORIZE)
async def show_duplicate_groups(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Render a bounded summary of duplicate groups pending manual review."""
    del context
    query = update.callback_query
    async with get_session() as session:
        result = await session.execute(
            select(
                DuplicateGroup.id,
                DuplicateGroup.match_reason,
                DuplicateGroup.created_at,
                func.count(duplicate_group_members.c.media_id).label("member_count"),
            )
            .outerjoin(
                duplicate_group_members,
                duplicate_group_members.c.group_id == DuplicateGroup.id,
            )
            .where(DuplicateGroup.status == DuplicateGroupStatus.PENDING_REVIEW.value)
            .group_by(
                DuplicateGroup.id,
                DuplicateGroup.match_reason,
                DuplicateGroup.created_at,
            )
            .order_by(DuplicateGroup.created_at.desc())
            .limit(20)
        )
        groups = result.all()

    await query.answer()
    if not groups:
        text = "🔍 כפילויות\n\nלא נמצאו קבוצות כפולות הממתינות לבדיקה."
    else:
        lines = ["🔍 כפילויות הממתינות לבדיקה", ""]
        for group in groups:
            reason = group.match_reason or "התאמת מטא־נתונים"
            lines.append(f"• קבוצה #{group.id}: {group.member_count} פריטים — {reason}")
        lines.append("")
        lines.append("הזיהוי מתבצע אוטומטית בעת קליטת מדיה חדשה.")
        text = "\n".join(lines)

    await query.edit_message_text(text, reply_markup=main_menu_keyboard())


def register_duplicate_handlers(application) -> None:
    """Register the duplicate-review entry point exposed in the main menu."""
    application.add_handler(
        CallbackQueryHandler(show_duplicate_groups, pattern=f"^{CB.DUPLICATES}$")
    )
