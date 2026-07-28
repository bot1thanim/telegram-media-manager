"""
app/database/models/setting.py
================================
SQLAlchemy model for the `settings` table.
Key-value store for runtime-configurable behaviour.
Values are NEVER hardcoded in application logic.
"""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON
from app.database.base import Base


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict | str | int | float | bool | None] = mapped_column(
        JSON, nullable=True
    )

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r} value={self.value!r}>"


# Default setting keys (used throughout the application)
class SettingKey:
    FLOOD_CONTROL_DELAY_SECONDS = "flood_control_delay_seconds"
    DEFAULT_PUBLISH_ORDER = "default_publish_order"
    BACKUP_FREQUENCY = "backup_frequency"
    SCHEDULED_PUBLISH_ENABLED = "scheduled_publish_enabled"
    SCHEMA_VERSION = "schema_version"


# Default values — applied during initial DB seed
SETTING_DEFAULTS: dict[str, object] = {
    SettingKey.FLOOD_CONTROL_DELAY_SECONDS: 3,
    SettingKey.DEFAULT_PUBLISH_ORDER: "random",
    SettingKey.BACKUP_FREQUENCY: "daily",
    SettingKey.SCHEDULED_PUBLISH_ENABLED: True,
    SettingKey.SCHEMA_VERSION: 1,
}
