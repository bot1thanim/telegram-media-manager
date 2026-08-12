"""Durable reports for historical import, live synchronization, and topic broadcast."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Integer, JSON, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SyncRunType(str, enum.Enum):
    HISTORICAL_IMPORT = "HISTORICAL_IMPORT"
    TOPIC_BROADCAST = "TOPIC_BROADCAST"


class SyncRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SyncRun(Base):
    """The immutable-by-convention end report for one synchronization operation."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=SyncRunStatus.RUNNING.value
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SyncRun id={self.id} type={self.run_type} status={self.status}>"
