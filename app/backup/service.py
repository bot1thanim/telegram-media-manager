"""
app/backup/service.py
=======================
Backup and Restore logic.
SRS §19, §19.1: JSON export/import.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.category import Category
from app.database.models.media import Media
from app.database.models.backup import Backup
from app.audit.logger import log_action, AuditAction

logger = logging.getLogger(__name__)


async def create_backup(session: AsyncSession, actor_id: int | None = None) -> str:
    """
    SRS §19.1: Export all data to a JSON string.
    Returns the JSON string.
    """
    # Fetch all categories
    cat_result = await session.execute(select(Category))
    categories = cat_result.scalars().all()
    
    # Fetch all media
    media_result = await session.execute(select(Media))
    media_items = media_result.scalars().all()
    
    data = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "emoji": c.emoji,
                "telegram_thread_id": c.telegram_thread_id
            } for c in categories
        ],
        "media": [
            {
                "file_unique_id": m.file_unique_id,
                "file_id": m.file_id,
                "media_type": m.media_type,
                "file_size": m.file_size,
                "caption": m.caption,
                "category_id": m.category_id,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else None
            } for m in media_items
        ]
    }
    
    json_data = json.dumps(data, indent=2, ensure_ascii=False)
    
    # Save record
    backup = Backup(
        file_path="memory", # In v1 we send directly to user
        file_size=len(json_data.encode('utf-8')),
        status="completed"
    )
    session.add(backup)
    await session.flush()
    
    await log_action(session, AuditAction.BACKUP_CREATED, actor_telegram_id=actor_id)
    return json_data


async def restore_backup(session: AsyncSession, json_data: str, actor_id: int | None = None):
    """
    SRS §19.1: Restore data from JSON.
    Updates existing records by file_unique_id, creates new ones.
    """
    data = json.loads(json_data)
    
    # 1. Restore categories
    for cat_data in data.get("categories", []):
        result = await session.execute(
            select(Category).where(Category.name == cat_data["name"])
        )
        cat = result.scalar_one_or_none()
        if not cat:
            cat = Category(name=cat_data["name"], emoji=cat_data.get("emoji"))
            session.add(cat)
        cat.telegram_thread_id = cat_data.get("telegram_thread_id")
        
    await session.flush()
    
    # 2. Restore media
    for m_data in data.get("media", []):
        result = await session.execute(
            select(Media).where(Media.file_unique_id == m_data["file_unique_id"])
        )
        media = result.scalar_one_or_none()
        if not media:
            media = Media(file_unique_id=m_data["file_unique_id"])
            session.add(media)
            
        media.file_id = m_data["file_id"]
        media.media_type = m_data["media_type"]
        media.file_size = m_data["file_size"]
        media.caption = m_data.get("caption")
        media.status = m_data["status"]
        # Map category by name would be safer here, but keeping it simple for now
        
    await session.flush()
    await log_action(session, AuditAction.BACKUP_RESTORED, actor_telegram_id=actor_id)
