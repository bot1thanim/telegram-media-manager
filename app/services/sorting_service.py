"""
app/services/sorting_service.py
==================================
Logic for sorting sessions and admin handoff.
SRS §10.2 (Handoff mechanism)
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.sorting_session import SortingSession
from app.database.models.admin import Admin
from app.audit.logger import log_action, AuditAction

logger = logging.getLogger(__name__)

# Session timeout for handoff (SRS §10.2: "active session")
SESSION_TIMEOUT_MINUTES = 15


async def get_active_session(session: AsyncSession) -> SortingSession | None:
    """Check if any admin has an active sorting session."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    result = await session.execute(
        select(SortingSession).where(SortingSession.updated_at > threshold).limit(1)
    )
    return result.scalar_one_or_none()


async def start_or_update_session(
    session: AsyncSession,
    admin_id: int,
    current_media_id: int
) -> SortingSession:
    """Start a new session or update existing one for the admin."""
    # Remove any old sessions for this admin
    await session.execute(
        delete(SortingSession).where(SortingSession.admin_telegram_id == admin_id)
    )
    
    new_session = SortingSession(
        admin_telegram_id=admin_id,
        current_media_id=current_media_id,
        updated_at=datetime.now(timezone.utc)
    )
    session.add(new_session)
    await session.flush()
    return new_session


async def end_session(session: AsyncSession, admin_id: int) -> None:
    """Clear session when admin exits sorting."""
    await session.execute(
        delete(SortingSession).where(SortingSession.admin_telegram_id == admin_id)
    )
    await session.flush()


async def handle_handoff(
    session: AsyncSession,
    new_admin_id: int,
    actor_name: str
) -> tuple[bool, SortingSession | None]:
    """
    SRS §10.2: Handle session handoff.
    Returns (needs_confirmation, active_session).
    """
    active = await get_active_session(session)
    
    if not active:
        return False, None
        
    if active.admin_telegram_id == new_admin_id:
        # Same admin resuming
        return False, active
        
    # Different admin active — needs confirmation
    return True, active


async def confirm_handoff(
    session: AsyncSession,
    new_admin_id: int,
    old_admin_id: int,
    media_id: int
) -> None:
    """Log the handoff and start new session."""
    await log_action(
        session,
        AuditAction.SORTING_SESSION_HANDOFF,
        actor_telegram_id=new_admin_id,
        details={
            "previous_admin_id": old_admin_id,
            "media_id": media_id
        }
    )
    await start_or_update_session(session, new_admin_id, media_id)
