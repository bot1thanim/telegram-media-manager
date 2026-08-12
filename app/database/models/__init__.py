"""
app/database/models/__init__.py
=================================
Imports all models so that Alembic and SQLAlchemy can discover them
when generating migrations and creating tables.
"""

from app.database.base import Base
from app.database.models.admin import Admin
from app.database.models.audit_log import AuditLog
from app.database.models.backup import Backup
from app.database.models.category import Category
from app.database.models.duplicate_group import (
    DuplicateGroup,
    DuplicateGroupStatus,
    duplicate_group_members,
)
from app.database.models.media import Media, MediaStatus, MediaType
from app.database.models.media_delivery import MediaDelivery, MediaDeliveryState
from app.database.models.publish_job import (
    PublishJob,
    PublishJobStatus,
    PublishQueueItem,
    PublishQueueItemState,
)
from app.database.models.sync_run import SyncRun, SyncRunStatus, SyncRunType
from app.database.models.topic_catalog import TopicCatalog
from app.database.models.setting import (
    SETTING_DEFAULTS,
    Setting,
    SettingKey,
)
from app.database.models.sorting_session import SortingSession
from app.database.models.tag import Tag, media_tags

__all__ = [
    "SETTING_DEFAULTS",
    "Admin",
    "AuditLog",
    "Backup",
    "Base",
    "Category",
    "DuplicateGroup",
    "DuplicateGroupStatus",
    "Media",
    "MediaDelivery",
    "MediaDeliveryState",
    "MediaStatus",
    "MediaType",
    "PublishJob",
    "PublishJobStatus",
    "PublishQueueItem",
    "PublishQueueItemState",
    "Setting",
    "SettingKey",
    "SortingSession",
    "SyncRun",
    "SyncRunStatus",
    "SyncRunType",
    "Tag",
    "TopicCatalog",
    "duplicate_group_members",
    "media_tags",
]
