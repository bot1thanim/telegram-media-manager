"""
app/database/engine.py
========================
Async SQLAlchemy engine and session factory.
All database access in the application goes through `get_session()`.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.base import Base

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str) -> None:
    """
    Initialise the async engine and session factory.
    Called once at application startup from app/main.py.
    """
    global _engine, _session_factory

    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,       # detect stale connections
        pool_size=5,
        max_overflow=10,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    logger.info("Database engine initialised.")


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine has not been initialised. Call init_engine() first.")
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a database session.

    Usage:
        async with get_session() as session:
            result = await session.execute(...)
    """
    if _session_factory is None:
        raise RuntimeError("Session factory has not been initialised. Call init_engine() first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """
    Create all tables defined in the models (used for testing / initial setup).
    In production, Alembic migrations handle schema changes.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("All tables created (or already exist).")


async def close_engine() -> None:
    """Dispose the engine — called on application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database engine closed.")
