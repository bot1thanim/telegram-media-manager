"""
app/database/models/sorting_session.py
=========================================
SQLAlchemy model for the `sorting_sessions` table.
Tracks the global sorting session state (one active at a time in v1).
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class SortingSession(Base):
    __tablename__ = "sorting_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_media_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    taken_over_from: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<SortingSession id={self.id} "
            f"admin={self.admin_telegram_id} "
            f"active={self.is_active} "
            f"current_media={self.current_media_id}>"
        )
