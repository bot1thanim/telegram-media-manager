"""Sorting-session lifecycle and controlled handoff logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.logger import AuditAction, log_action
from app.database.models.sorting_session import SortingSession

SESSION_TIMEOUT_MINUTES = 15


def _active_threshold() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=SESSION_TIMEOUT_MINUTES)


async def get_active_session(session: AsyncSession) -> SortingSession | None:
    """Return the currently active non-expired session, if one exists."""
    result = await session.execute(
        select(SortingSession)
        .where(
            SortingSession.is_active.is_(True),
            SortingSession.last_activity_at > _active_threshold(),
        )
        .order_by(SortingSession.last_activity_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_session_for_admin(
    session: AsyncSession, admin_id: int
) -> SortingSession | None:
    """Return the active session that belongs to the requesting administrator."""
    result = await session.execute(
        select(SortingSession).where(
            SortingSession.admin_telegram_id == admin_id,
            SortingSession.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def start_or_update_session(
    session: AsyncSession,
    admin_id: int,
    current_media_id: int,
    *,
    taken_over_from: int | None = None,
) -> SortingSession:
    """Create or update the requester's active sorting session."""
    now = datetime.now(timezone.utc)
    existing = await get_session_for_admin(session, admin_id)
    if existing is not None:
        existing.current_media_id = current_media_id
        existing.last_activity_at = now
        existing.is_active = True
        if taken_over_from is not None:
            existing.taken_over_from = taken_over_from
        await session.flush()
        return existing

    new_session = SortingSession(
        admin_telegram_id=admin_id,
        current_media_id=current_media_id,
        is_active=True,
        taken_over_from=taken_over_from,
        last_activity_at=now,
    )
    session.add(new_session)
    await session.flush()
    return new_session


async def end_session(session: AsyncSession, admin_id: int) -> None:
    """Mark the administrator's active session inactive without deleting audit context."""
    existing = await get_session_for_admin(session, admin_id)
    if existing is not None:
        existing.is_active = False
        existing.current_media_id = None
        existing.last_activity_at = datetime.now(timezone.utc)
        await session.flush()


async def handle_handoff(
    session: AsyncSession, new_admin_id: int, actor_name: str
) -> tuple[bool, SortingSession | None]:
    """Determine whether another live session must be explicitly taken over."""
    del actor_name  # Display names are resolved by the Telegram handler when needed.
    active = await get_active_session(session)
    if active is None or active.admin_telegram_id == new_admin_id:
        return False, active
    return True, active


async def confirm_handoff(
    session: AsyncSession, new_admin_id: int, old_admin_id: int, media_id: int
) -> None:
    """Deactivate the prior session and transfer the selected media to the new owner."""
    previous = await get_session_for_admin(session, old_admin_id)
    if previous is not None:
        previous.is_active = False
        previous.last_activity_at = datetime.now(timezone.utc)
    await log_action(
        session,
        AuditAction.SORTING_SESSION_HANDOFF,
        actor_telegram_id=new_admin_id,
        details={"previous_admin_id": old_admin_id, "media_id": media_id},
    )
    await start_or_update_session(
        session,
        new_admin_id,
        media_id,
        taken_over_from=old_admin_id,
    )
