"""Regression tests for production database URL and engine lifecycle behavior."""

import pytest
from sqlalchemy.engine import make_url

from app.config import Config, normalize_database_url
from app.database.engine import close_engine, get_engine, init_engine
from app.scheduler.manager import _to_sync_database_url


def test_normalize_database_url_converts_libpq_sslmode_for_asyncpg() -> None:
    normalized = normalize_database_url(
        "postgresql://user:password@aws-eu.pooler.supabase.com:5432/postgres?sslmode=require"
    )
    url = make_url(normalized)

    assert url.drivername == "postgresql+asyncpg"
    assert url.query["ssl"] == "require"
    assert "sslmode" not in url.query


def test_source_and_target_group_ids_fall_back_to_legacy_group(monkeypatch) -> None:
    monkeypatch.delenv("SOURCE_GROUP_CHAT_ID", raising=False)
    monkeypatch.delenv("TARGET_GROUP_CHAT_ID", raising=False)

    runtime_config = Config()

    assert runtime_config.SOURCE_GROUP_CHAT_ID == runtime_config.GROUP_CHAT_ID
    assert runtime_config.TARGET_GROUP_CHAT_ID == runtime_config.GROUP_CHAT_ID


def test_source_and_target_group_ids_accept_explicit_values(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_GROUP_CHAT_ID", "-100200")
    monkeypatch.setenv("TARGET_GROUP_CHAT_ID", "-100300")

    runtime_config = Config()

    assert runtime_config.SOURCE_GROUP_CHAT_ID == -100200
    assert runtime_config.TARGET_GROUP_CHAT_ID == -100300


def test_scheduler_url_converts_asyncpg_ssl_to_psycopg_sslmode() -> None:
    scheduler_url = _to_sync_database_url(
        "postgresql+asyncpg://user:password@aws-eu.pooler.supabase.com:5432/postgres?ssl=require"
    )
    url = make_url(scheduler_url)

    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"
    assert "ssl" not in url.query


@pytest.mark.asyncio
async def test_engine_lifecycle_resets_global_state() -> None:
    init_engine("sqlite+aiosqlite:///:memory:")
    assert get_engine() is not None

    await close_engine()

    with pytest.raises(RuntimeError, match="has not been initialized"):
        get_engine()

    init_engine("sqlite+aiosqlite:///:memory:")
    await close_engine()


def test_http_transport_loggers_do_not_emit_sensitive_urls_at_info_level() -> None:
    """Telegram's HTTP URLs contain a bot token and must not reach Render logs."""
    import logging

    import app.main  # noqa: F401 - importing configures the application loggers

    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert not logging.getLogger("httpcore").isEnabledFor(logging.INFO)
