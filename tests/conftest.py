"""
tests/conftest.py
==================
Shared pytest fixtures for unit and integration tests.
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.database.models  # noqa: F401 — register all models
from app.database.base import Base

# ─── In-memory SQLite database for unit tests ─────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create an in-memory SQLite engine for each test function."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    """Yield a database session for each test, with automatic rollback."""
    factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with factory() as session:
        yield session
        await session.rollback()


# ─── Mock Telegram Bot ────────────────────────────────────────────────────────


@pytest.fixture
def mock_bot():
    """A mock Telegram Bot instance."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_video = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_document = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.answer_callback_query = AsyncMock()
    bot.set_reaction = AsyncMock()
    return bot


# ─── Owner ID fixture ─────────────────────────────────────────────────────────


@pytest.fixture
def owner_id() -> int:
    return 7706183809


@pytest.fixture
def non_owner_id() -> int:
    return 9999999999
