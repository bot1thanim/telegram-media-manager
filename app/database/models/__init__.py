"""
app/database/models/__init__.py
=================================
Imports all models so that Alembic and SQLAlchemy can discover them
when generating migrations and creating tables.
"""

from app.database.base import Base  # noqa: F401
from app.database.models.category import Category  # noqa: F401
from app.database.models.media import Media, MediaStatus, MediaType  # noqa: F401
from app.database.models.tag import Tag, media_tags  # noqa: F401
from app.database.models.duplicate_group import (  # noqa: F401
    DuplicateGroup, DuplicateGroupStatus, duplicate_group_members
)
from app.database.models.admin import Admin  # noqa: F401
from app.database.models.sorting_session import SortingSession  # noqa: F401
from app.database.models.publish_job import (  # noqa: F401
    PublishJob, PublishQueueItem, PublishJobStatus, PublishQueueItemState
)
from app.database.models.audit_log import AuditLog  # noqa: F401
from app.database.models.setting import Setting, SettingKey, SETTING_DEFAULTS  # noqa: F401
from app.database.models.backup import Backup  # noqa: F401

__all__ = [
    "Base",
    "Category",
    "Media", "MediaStatus", "MediaType",
    "Tag", "media_tags",
    "DuplicateGroup", "DuplicateGroupStatus", "duplicate_group_members",
    "Admin",
    "SortingSession",
    "PublishJob", "PublishQueueItem", "PublishJobStatus", "PublishQueueItemState",
    "AuditLog",
    "Setting", "SettingKey", "SETTING_DEFAULTS",
    "Backup",
]
