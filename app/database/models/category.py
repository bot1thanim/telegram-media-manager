"""
app/database/models/category.py
================================
SQLAlchemy model for the `categories` table.
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint(
            "source_group_id",
            "source_thread_id",
            name="uq_categories_source_group_thread",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # Target topic thread retained under its existing name for backward compatibility.
    telegram_thread_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True
    )
    source_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    emoji: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_missing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    media_items: Mapped[list] = relationship(
        "Media", back_populates="category", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r}>"
