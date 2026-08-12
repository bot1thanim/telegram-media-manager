"""Unit tests for deterministic topic matching and source-media ingestion."""

from types import SimpleNamespace

import pytest

from app.sync.matching import choose_best_topic_match, normalize_topic_name
from app.sync.services import ensure_source_category, ingest_source_media


def test_normalize_topic_name_removes_hebrew_marks_and_punctuation():
    assert normalize_topic_name("  סִדרות — טורקיות! ") == "סדרות טורקיות"


def test_topic_match_handles_hebrew_singular_plural_variants():
    topics = [SimpleNamespace(id=14, name="ישראליות")]

    match = choose_best_topic_match("ישראלי", topics)

    assert match.is_match is True
    assert match.topic_id == 14
    assert match.method == "canonical_exact"


def test_topic_match_handles_english_plural_variants():
    topics = [SimpleNamespace(id=7, name="Movies")]

    match = choose_best_topic_match("movie", topics)

    assert match.is_match is True
    assert match.topic_id == 7


def test_topic_match_rejects_ambiguous_fuzzy_candidates():
    topics = [
        SimpleNamespace(id=1, name="סרטים ישראלים"),
        SimpleNamespace(id=2, name="סרטים ישראליות"),
    ]

    match = choose_best_topic_match("סרטים ישראל", topics)

    assert match.is_match is False
    assert match.ambiguous is True


@pytest.mark.asyncio
async def test_source_topic_creates_category_and_ingests_media_once(db_session):
    category, created = await ensure_source_category(
        db_session,
        source_group_id=-100123,
        source_thread_id=44,
        topic_name="סדרות",
        actor_id=1,
    )
    assert created is True
    assert category.name == "סדרות"

    first = await ingest_source_media(
        db_session,
        file_id="bot-file-1",
        file_unique_id="source-message-one",
        media_type="video",
        file_size=1234,
        caption="פרק ראשון",
        duration=10,
        uploader_id=7,
        source_group_id=-100123,
        source_thread_id=44,
        source_message_id=90,
        category_id=category.id,
    )
    duplicate = await ingest_source_media(
        db_session,
        file_id="bot-file-1-updated",
        file_unique_id="source-message-one",
        media_type="video",
        file_size=1234,
        caption="פרק ראשון",
        duration=10,
        uploader_id=7,
        source_group_id=-100123,
        source_thread_id=44,
        source_message_id=90,
        category_id=category.id,
    )

    assert first.is_new is True
    assert first.media.category_id == category.id
    assert first.media.status == "READY_TO_PUBLISH"
    assert duplicate.is_new is False
    assert duplicate.duplicate_reason == "source_message"
