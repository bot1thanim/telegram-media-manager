"""Per-destination delivery state used by the all-categories broadcaster."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MediaDeliveryState(str, enum.Enum):
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class MediaDelivery(Base):
    """One media item's delivery outcome for one topic in one target chat."""

    __tablename__ = "media_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "media_id",
            "target_chat_id",
            "target_thread_id",
            name="uq_media_delivery_destination",
        ),
        Index("ix_media_deliveries_run", "sync_run_id", "state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    sync_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sync_runs.id", ondelete="SET NULL"), nullable=True
    )
    target_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_thread_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default=MediaDeliveryState.SENDING.value
    )
    target_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<MediaDelivery id={self.id} media={self.media_id} state={self.state}>"
