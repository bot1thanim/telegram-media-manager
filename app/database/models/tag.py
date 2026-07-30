"""
app/database/models/tag.py
===========================
SQLAlchemy models for `tags` and `media_tags` (many-to-many join table).
"""

from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Integer, Table, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


# Many-to-many association table
media_tags = Table(
    "media_tags",
    Base.metadata,
    Column(
        "media_id",
        Integer,
        ForeignKey("media.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    media_items: Mapped[list] = relationship(
        "Media", secondary="media_tags", back_populates="tags", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name={self.name!r}>"
