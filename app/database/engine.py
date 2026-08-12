"""
app/database/engine.py
========================
Async SQLAlchemy engine and transaction-scoped session factory.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

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
    """Create the single application-owned asynchronous database engine."""
    global _engine, _session_factory

    if _engine is not None:
        raise RuntimeError("Database engine is already initialized.")

    engine_options: dict[str, object] = {"echo": False}
    if database_url.startswith("postgresql+asyncpg://"):
        engine_options.update(
            {
                "pool_pre_ping": True,
                "pool_size": 3,
                "max_overflow": 2,
                "pool_timeout": 30,
                "pool_recycle": 1800,
                "connect_args": {"timeout": 15, "command_timeout": 30},
            }
        )

    _engine = create_async_engine(database_url, **engine_options)
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    logger.info("Database engine initialized.")


def get_engine() -> AsyncEngine:
    """Return the initialized engine or fail loudly on an invalid lifecycle."""
    if _engine is None:
        raise RuntimeError(
            "Database engine has not been initialized. Call init_engine() first."
        )
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield one transaction-scoped async session with rollback on failure."""
    if _session_factory is None:
        raise RuntimeError(
            "Session factory has not been initialized. Call init_engine() first."
        )

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """Create ORM tables for isolated tests; production uses Alembic migrations."""
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    logger.info("All tables created or already exist.")


async def close_engine() -> None:
    """Dispose all pooled connections and reset global lifecycle state."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
    logger.info("Database engine closed.")
