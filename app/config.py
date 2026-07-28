"""
app/config.py
=============
Loads all required environment variables at startup.
Crashes immediately with a clear error message if any required variable is missing.
NEVER provides silent defaults for secrets.
"""

import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

logger = logging.getLogger(__name__)


def _require(name: str) -> str:
    """Read a required environment variable. Crash loudly if missing."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"[STARTUP ERROR] Required environment variable \'{name}\' is missing or empty. "
            f"Check your .env file or Render environment settings."
        )
    return value


def _optional(name: str, default: str) -> str:
    """Read an optional environment variable with a safe default."""
    return os.environ.get(name, default)


class Config:
    """Central configuration object. Instantiated once at startup."""

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
        self.DATABASE_URL = _require("DATABASE_URL")
        self.WEBHOOK_BASE_URL = _require("WEBHOOK_BASE_URL")

        # Numeric fields — validate type
        try:
            self.OWNER_TELEGRAM_ID = int(_require("OWNER_TELEGRAM_ID"))
        except ValueError:
            raise RuntimeError(
                "[STARTUP ERROR] OWNER_TELEGRAM_ID must be a numeric Telegram User ID."
            )

        try:
            self.GROUP_CHAT_ID = int(_require("GROUP_CHAT_ID"))
        except ValueError:
            raise RuntimeError(
                "[STARTUP ERROR] GROUP_CHAT_ID must be a numeric Telegram Chat ID."
            )

        try:
            self.GENERAL_TOPIC_THREAD_ID = int(_require("GENERAL_TOPIC_THREAD_ID"))
        except ValueError:
            raise RuntimeError(
                "[STARTUP ERROR] GENERAL_TOPIC_THREAD_ID must be a numeric thread ID."
            )

        self.LOG_LEVEL = _optional("LOG_LEVEL", "INFO").upper()

        # Normalise DATABASE_URL: SQLAlchemy async driver requires asyncpg
        if self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = self.DATABASE_URL.replace(
                "postgres://", "postgresql+asyncpg://", 1
            )
        elif (
            self.DATABASE_URL.startswith("postgresql://")
            and "+asyncpg" not in self.DATABASE_URL
        ):
            self.DATABASE_URL = self.DATABASE_URL.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )

        logger.info("Configuration loaded successfully.")

    @property
    def webhook_path(self) -> str:
        """The URL path that Telegram will POST updates to."""
        return "/webhook"

    @property
    def webhook_url(self) -> str:
        """Full public URL for the Telegram Webhook."""
        base = self.WEBHOOK_BASE_URL.rstrip("/")
        return f"{base}{self.webhook_path}"


# Singleton — imported everywhere as `from app.config import config`
config = Config()
