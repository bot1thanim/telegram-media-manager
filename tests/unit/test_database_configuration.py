"""Regression tests for production database URL and engine lifecycle behavior."""

import pytest
from sqlalchemy.engine import make_url

from app.config import normalize_database_url
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
