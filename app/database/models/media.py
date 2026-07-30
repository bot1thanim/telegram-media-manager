"""
app/database/models/media.py
=============================
SQLAlchemy model for the `media` table.
Includes the MediaStatus enum that represents the full state machine.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class MediaStatus(str, enum.Enum):
    """
    State machine for a media item's lifecycle.

    NEW → WAITING_CATEGORIZATION → CATEGORIZED → READY_TO_PUBLISH → PUBLISHED
    Any state → DELETED (soft delete / recycle bin)
    Any publish attempt with expired file_id → BROKEN
    """

    NEW = "NEW"
    WAITING_CATEGORIZATION = "WAITING_CATEGORIZATION"
    CATEGORIZED = "CATEGORIZED"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHED = "PUBLISHED"
    DELETED = "DELETED"
    BROKEN = "BROKEN"


class MediaType(str, enum.Enum):
    VIDEO = "video"
    PHOTO = "photo"


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        UniqueConstraint("file_unique_id", name="uq_media_file_unique_id"),
        Index("ix_media_category_id", "category_id"),
        Index("ix_media_status_category", "status", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_unique_id: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)  # "video" | "photo"
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=MediaStatus.NEW.value
    )
    is_duplicate_of: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="RESTRICT"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    published_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Status before deletion — used to restore to correct state
    pre_delete_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    category: Mapped["Category"] = relationship(  # noqa: F821
        "Category", back_populates="media_items", lazy="select"
    )
    duplicate_parent: Mapped["Media | None"] = relationship(
        "Media", remote_side="Media.id", foreign_keys=[is_duplicate_of], lazy="select"
    )
    tags: Mapped[list] = relationship(
        "Tag", secondary="media_tags", back_populates="media_items", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Media id={self.id} type={self.media_type} status={self.status}>"
