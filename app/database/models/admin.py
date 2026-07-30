"""
app/database/models/admin.py
==============================
SQLAlchemy model for the `admins` table.
Stores Admins and Viewers (not the Owner — Owner is defined by env var).
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Integer, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow():
    return datetime.now(timezone.utc)


class AdminRole(str):
    ADMIN = "admin"
    VIEWER = "viewer"


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="admin")
    # JSON object with permission keys from SRS §7.1
    # e.g. {"import": true, "categorize": true, "publish": false, ...}
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    added_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Admin id={self.id} user_id={self.telegram_user_id} role={self.role}>"
