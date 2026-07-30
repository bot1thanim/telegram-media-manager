"""
app/database/models/duplicate_group.py
========================================
SQLAlchemy models for `duplicate_groups` and `duplicate_group_members`.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Integer, Table, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class DuplicateGroupStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    RESOLVED = "RESOLVED"


# Association table for group members
duplicate_group_members = Table(
    "duplicate_group_members",
    Base.metadata,
    Column(
        "media_id",
        Integer,
        ForeignKey("media.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column(
        "group_id",
        Integer,
        ForeignKey("duplicate_groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=DuplicateGroupStatus.PENDING_REVIEW.value
    )
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    members: Mapped[list] = relationship(
        "Media",
        secondary="duplicate_group_members",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<DuplicateGroup id={self.id} status={self.status}>"
