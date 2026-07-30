"""
app/database/models/publish_job.py
====================================
SQLAlchemy models for `publish_jobs` and `publish_queue_items`.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class PublishJobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PublishQueueItemState(str, enum.Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PublishJob(Base):
    __tablename__ = "publish_jobs"
    __table_args__ = (
        Index("ix_publish_jobs_status", "status"),
        Index("ix_publish_jobs_scheduled", "is_scheduled", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=PublishJobStatus.QUEUED.value
    )
    scope: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # "all" or category name
    scope_category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    order_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    scheduled_cron: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_per_run: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    queue_items: Mapped[list["PublishQueueItem"]] = relationship(
        "PublishQueueItem",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<PublishJob id={self.id} status={self.status}>"


class PublishQueueItem(Base):
    __tablename__ = "publish_queue_items"
    __table_args__ = (
        UniqueConstraint("job_id", "media_id", name="uq_pqi_job_media"),
        UniqueConstraint("job_id", "position", name="uq_pqi_job_position"),
        Index("ix_pqi_job_state", "job_id", "state"),
        Index("ix_pqi_job_position", "job_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("publish_jobs.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default=PublishQueueItemState.PENDING.value
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Relationships
    job: Mapped["PublishJob"] = relationship("PublishJob", back_populates="queue_items")

    def __repr__(self) -> str:
        return (
            f"<PublishQueueItem id={self.id} "
            f"job={self.job_id} media={self.media_id} "
            f"pos={self.position} state={self.state}>"
        )
