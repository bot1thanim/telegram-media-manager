"""
app/config.py
=============
Loads and validates environment variables at startup.

Secrets are supplied exclusively by the runtime environment.  The database URL
is converted to the SQLAlchemy asyncpg dialect without logging its value.
"""

import logging
import os

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# Load a local developer file when present. Render supplies environment variables
# directly, and python-dotenv does not override them by default.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

logger = logging.getLogger(__name__)


def _require(name: str) -> str:
    """Read a required environment variable and fail loudly when it is absent."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"[STARTUP ERROR] Required environment variable '{name}' is missing or empty. "
            "Check your local .env file or Render environment settings."
        )
    return value


def _optional(name: str, default: str) -> str:
    """Read an optional environment variable with a safe default."""
    return os.environ.get(name, default)


def normalize_database_url(raw_url: str) -> str:
    """Return a PostgreSQL URL compatible with SQLAlchemy's asyncpg dialect.

    Supabase and many libpq clients express TLS policy as ``sslmode``. asyncpg
    expects the equivalent ``ssl`` option, so the value is translated here.
    Passwords remain percent-encoded and are never written to logs.
    """
    try:
        url = make_url(raw_url.strip())
    except (ArgumentError, ValueError) as exc:
        raise RuntimeError(
            "[STARTUP ERROR] DATABASE_URL must be a valid PostgreSQL connection URL."
        ) from exc

    if url.get_backend_name() not in {"postgresql", "postgres"}:
        raise RuntimeError(
            "[STARTUP ERROR] DATABASE_URL must use a PostgreSQL connection URL."
        )

    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if sslmode is not None and "ssl" not in query:
        query["ssl"] = sslmode

    return url.set(
        drivername="postgresql+asyncpg",
        query=query,
    ).render_as_string(hide_password=False)


class Config:
    """Central configuration object instantiated once during process startup."""

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str
    OWNER_TELEGRAM_ID: int
    WEBHOOK_SECRET_TOKEN: str
    GROUP_CHAT_ID: int
    GENERAL_TOPIC_THREAD_ID: int

    # --- Database ---
    DATABASE_URL: str

    # --- Deployment ---
    WEBHOOK_BASE_URL: str

    # --- Application ---
    LOG_LEVEL: str

    def __init__(self) -> None:
        self.TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
        self.WEBHOOK_SECRET_TOKEN = _require("WEBHOOK_SECRET_TOKEN")
        self.DATABASE_URL = normalize_database_url(_require("DATABASE_URL"))
        self.WEBHOOK_BASE_URL = _require("WEBHOOK_BASE_URL")

        try:
            self.OWNER_TELEGRAM_ID = int(_require("OWNER_TELEGRAM_ID"))
        except ValueError as exc:
            raise RuntimeError(
                "[STARTUP ERROR] OWNER_TELEGRAM_ID must be a numeric Telegram User ID."
            ) from exc

        try:
            self.GROUP_CHAT_ID = int(_require("GROUP_CHAT_ID"))
        except ValueError as exc:
            raise RuntimeError(
                "[STARTUP ERROR] GROUP_CHAT_ID must be a numeric Telegram Chat ID."
            ) from exc

        try:
            self.GENERAL_TOPIC_THREAD_ID = int(_require("GENERAL_TOPIC_THREAD_ID"))
        except ValueError as exc:
            raise RuntimeError(
                "[STARTUP ERROR] GENERAL_TOPIC_THREAD_ID must be a numeric thread ID."
            ) from exc

        self.LOG_LEVEL = _optional("LOG_LEVEL", "INFO").upper()
        logger.info("Configuration loaded successfully.")

    @property
    def webhook_path(self) -> str:
        """The URL path that Telegram uses to POST updates."""
        return "/webhook"

    @property
    def webhook_url(self) -> str:
        """Return the full public Telegram webhook URL."""
        return f"{self.WEBHOOK_BASE_URL.rstrip('/')}{self.webhook_path}"


# Singleton imported by application modules.
config = Config()
