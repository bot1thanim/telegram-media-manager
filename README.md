# Telegram Media Manager Bot

A full-featured Telegram bot for managing a video, photo, and document library using Telegram Forum Topics as categories. It supports a one-time historical import from a source forum group, live source synchronization, and a name-matched broadcast to a separate target forum group.

## Architecture

- **Language**: Python 3.12
- **Framework**: python-telegram-bot v21+ (async, Webhook mode)
- **Database**: PostgreSQL (async via SQLAlchemy 2.0 + asyncpg)
- **Migrations**: Alembic
- **Scheduler**: APScheduler with SQLAlchemyJobStore
- **Deployment**: Render Web Service + Supabase PostgreSQL

## Local Development Setup

### Prerequisites

- Python 3.12+
- PostgreSQL database (local or Supabase)

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/telegram-media-manager.git
cd telegram-media-manager

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your actual values
```

### Environment Variables

See `.env.example` for all required variables.

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot token from @BotFather |
| `OWNER_TELEGRAM_ID` | ✅ | Numeric Telegram User ID of the owner |
| `WEBHOOK_SECRET_TOKEN` | ✅ | Secret for validating webhook requests |
| `GROUP_CHAT_ID` | ✅ | Legacy managed-group ID; used as the source and target fallback for backward compatibility |
| `SOURCE_GROUP_CHAT_ID` | ❌ | Source Forum group ID for media ingestion; defaults to `GROUP_CHAT_ID` |
| `TARGET_GROUP_CHAT_ID` | ❌ | Target Forum group ID for publishing; defaults to `GROUP_CHAT_ID` |
| `GENERAL_TOPIC_THREAD_ID` | ✅ | Thread ID of the General topic (usually 1) |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `WEBHOOK_BASE_URL` | ✅ | Public URL of this service |
| `TELEGRAM_API_ID` | Local importer only | Telegram User API application ID; never configure in Render |
| `TELEGRAM_API_HASH` | Local importer only | Telegram User API application secret; never configure in Render |
| `TELEGRAM_IMPORT_SESSION_PATH` | ❌ | Local-only Telethon session location; defaults outside the repository |
| `LOG_LEVEL` | ❌ | Logging level (default: INFO) |

### Running Locally

For local development, you need a public URL for the Webhook. Use [ngrok](https://ngrok.com/):

```bash
# Start ngrok tunnel
ngrok http 8080

# Set WEBHOOK_BASE_URL to the ngrok URL in your .env
# Then run the bot
python -m app.main
```

### Topic Synchronization

The live webhook catalogues newly created and renamed topics in the configured source and target groups. New videos, photos, and documents sent under a catalogued source topic are placed directly in the matching internal category and are made ready for publication.

For existing history, run the one-time local importer from a machine you control. Create a Telegram User API application at [my.telegram.org](https://my.telegram.org), set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` only in your local `.env`, and then run:

```bash
python -m app.sync.topic_importer
```

The command prompts locally for Telegram authorization when needed. Do not send an OTP, password, session file, API hash, or import session string through Telegram, GitHub, Render, or chat. The importer records source and target topic catalogs plus source media identities, then the bot's **📤 שלח לכל הקטגוריות** button matches target names, creates a missing target topic when permitted, and sends category media with a durable exception report. Full matching, duplicate, and recovery rules are documented in [docs/TOPIC_SYNC_ARCHITECTURE.md](docs/TOPIC_SYNC_ARCHITECTURE.md).

The bot must be a member of both groups. In the target group, grant it permission to manage topics and send media. In the source group, disable Privacy Mode in BotFather if the bot must receive ordinary member messages live.

### Running Tests

```bash
pytest tests/unit/ -v
```

## Deployment on Render

1. Push code to GitHub
2. Create a new Web Service on Render, connected to your GitHub repo
3. Set all environment variables in Render dashboard
4. Render will auto-deploy on every push to `main`

## Database Migrations

```bash
# Generate a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Project Structure

```
telegram-media-manager/
├── app/
│   ├── main.py                    # Entry point
│   ├── config.py                  # Environment variables + startup check
│   ├── telegram/
│   │   ├── webhook_server.py      # /webhook + /health endpoints
│   │   ├── handlers/              # Telegram update handlers
│   │   ├── keyboards.py           # All InlineKeyboardMarkup builders
│   │   └── messages.py            # All user-facing message texts (Hebrew)
│   ├── database/
│   │   ├── engine.py              # Async SQLAlchemy engine
│   │   ├── base.py                # DeclarativeBase
│   │   ├── models/                # One model per table
│   │   └── migrations/            # Alembic migrations
│   ├── services/                  # Business logic (testable without Telegram)
│   ├── duplicate_detector/        # Isolated duplicate detection module
│   ├── publishing/                # Publish queue builder and worker
│   ├── sync/                      # Topic catalog, matching, historical import, broadcast
│   ├── scheduler/                 # APScheduler setup and jobs
│   ├── backup/                    # JSON export/import
│   └── audit/                     # Central audit logging
└── tests/
    ├── unit/                      # Unit tests for services/
    └── integration/               # Integration tests (real Telegram group)
```
