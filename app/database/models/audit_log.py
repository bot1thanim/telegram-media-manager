"""
app/database/models/audit_log.py
==================================
SQLAlchemy model for the `audit_log` table.
Every state-changing action writes one row here.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Index, Integer, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_actor_created", "actor_telegram_id", "created_at"),
        Index("ix_audit_action_created", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_media_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action!r} actor={self.actor_telegram_id}>"
