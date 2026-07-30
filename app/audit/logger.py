"""
app/audit/logger.py
====================
Central audit logging function.
Every state-changing action in the system calls log_action() — never writes
to audit_log directly from handlers or services.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    session: AsyncSession,
    action: str,
    actor_telegram_id: int | None = None,
    target_media_id: int | None = None,
    target_category_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Write one audit log entry.

    Parameters
    ----------
    session:
        Active SQLAlchemy async session (will be flushed but not committed here —
        the caller's session context manager handles commit/rollback).
    action:
        One of the action constants defined in AuditAction below.
    actor_telegram_id:
        Telegram User ID of the person who triggered the action.
    target_media_id:
        Primary key of the affected media row, if applicable.
    target_category_id:
        Primary key of the affected category row, if applicable.
    details:
        Arbitrary JSON-serialisable dict with extra context.
    """
    entry = AuditLog(
        action=action,
        actor_telegram_id=actor_telegram_id,
        target_media_id=target_media_id,
        target_category_id=target_category_id,
        details=details,
    )
    session.add(entry)
    await session.flush()
    logger.debug("Audit: %s by %s", action, actor_telegram_id)


class AuditAction:
    """
    Catalogue of all audit action strings (SRS §31).
    Using a class of constants prevents typos and enables IDE auto-complete.
    """

    MEDIA_IMPORTED = "MEDIA_IMPORTED"
    MEDIA_IMPORTED_DIRECT_TO_CATEGORY = "MEDIA_IMPORTED_DIRECT_TO_CATEGORY"
    MEDIA_CATEGORIZED = "MEDIA_CATEGORIZED"
    MEDIA_DELETED = "MEDIA_DELETED"
    MEDIA_RESTORED = "MEDIA_RESTORED"
    MEDIA_PERMANENTLY_DELETED = "MEDIA_PERMANENTLY_DELETED"
    MEDIA_MARKED_READY = "MEDIA_MARKED_READY"

    CATEGORY_CREATED = "CATEGORY_CREATED"
    CATEGORY_RENAMED = "CATEGORY_RENAMED"
    CATEGORY_DELETED = "CATEGORY_DELETED"
    CATEGORY_MERGED = "CATEGORY_MERGED"
    CATEGORY_LINKED_TOPIC = "CATEGORY_LINKED_TOPIC"
    CATEGORY_DUPLICATED = "CATEGORY_DUPLICATED"
    CATEGORY_ITEMS_TRANSFERRED = "CATEGORY_ITEMS_TRANSFERRED"

    DUPLICATE_GROUP_CREATED = "DUPLICATE_GROUP_CREATED"
    DUPLICATE_RESOLVED = "DUPLICATE_RESOLVED"

    PUBLISH_JOB_STARTED = "PUBLISH_JOB_STARTED"
    PUBLISH_JOB_PAUSED = "PUBLISH_JOB_PAUSED"
    PUBLISH_JOB_RESUMED = "PUBLISH_JOB_RESUMED"
    PUBLISH_JOB_STOPPED = "PUBLISH_JOB_STOPPED"
    PUBLISH_JOB_COMPLETED = "PUBLISH_JOB_COMPLETED"
    PUBLISH_ITEM_SENT = "PUBLISH_ITEM_SENT"
    PUBLISH_ITEM_FAILED = "PUBLISH_ITEM_FAILED"
    PUBLISH_JOB_RESUMED_AFTER_RESTART = "PUBLISH_JOB_RESUMED_AFTER_RESTART"

    ADMIN_ADDED = "ADMIN_ADDED"
    ADMIN_REMOVED = "ADMIN_REMOVED"
    ADMIN_PERMISSIONS_CHANGED = "ADMIN_PERMISSIONS_CHANGED"

    BACKUP_CREATED = "BACKUP_CREATED"
    BACKUP_RESTORED = "BACKUP_RESTORED"

    UNAUTHORIZED_ACCESS_ATTEMPT = "UNAUTHORIZED_ACCESS_ATTEMPT"
    SORTING_SESSION_HANDOFF = "SORTING_SESSION_HANDOFF"
    ERROR = "ERROR"
