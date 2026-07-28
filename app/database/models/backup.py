"""
app/database/models/backup.py
================================
SQLAlchemy model for the `backups` table.
Records metadata about each backup operation.
"""

from datetime import datetime, timezone
from sqlalchemy import BigInteger, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import TIMESTAMP
from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    triggered_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)  # "manual" | "auto"
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    categories_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    media_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Backup id={self.id} type={self.trigger_type} at={self.created_at}>"
