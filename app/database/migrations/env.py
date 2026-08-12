"""
Alembic environment configuration for async SQLAlchemy.
Reads DATABASE_URL from environment variable.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# Import all models so Alembic can detect them
import app.database.models  # noqa: F401 — registers all models
from app.database.base import Base

config = context.config
fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Return a PostgreSQL URL compatible with SQLAlchemy's asyncpg dialect."""
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    url = make_url(raw_url)
    if url.get_backend_name() not in {"postgresql", "postgres"}:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL connection URL.")

    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if sslmode is not None and "ssl" not in query:
        query["ssl"] = sslmode
    return url.set(
        drivername="postgresql+asyncpg",
        query=query,
    ).render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(get_url(), echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
