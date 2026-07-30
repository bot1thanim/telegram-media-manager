"""
tests/unit/test_core_services.py
==================================
Unit tests for category_service and media_service.
"""

import pytest

from app.services.category_service import (
    create_category,
    delete_category,
    get_all_categories,
)
from app.services.media_service import MediaStatus, categorize_media, import_media


@pytest.mark.asyncio
async def test_category_lifecycle(db_session):
    # Create
    cat = await create_category(db_session, "Test Cat", emoji="🎬")
    assert cat.name == "Test Cat"
    assert cat.emoji == "🎬"

    # List
    cats = await get_all_categories(db_session)
    assert len(cats) == 1

    # Delete
    await delete_category(db_session, cat.id)
    cats = await get_all_categories(db_session)
    assert len(cats) == 0


@pytest.mark.asyncio
async def test_media_import_and_categorize(db_session):
    # Import
    media, is_new = await import_media(
        db_session,
        file_id="fid1",
        file_unique_id="fuid1",
        media_type="video",
        file_size=1000,
    )
    assert is_new is True
    assert media.status == MediaStatus.WAITING_CATEGORIZATION.value

    # Create category
    cat = await create_category(db_session, "Movies")

    # Categorize
    updated_media = await categorize_media(db_session, media.id, cat.id)
    assert updated_media.category_id == cat.id
    assert updated_media.status == MediaStatus.READY_TO_PUBLISH.value
