# Telegram Media Manager Bot

A full-featured Telegram bot for managing a video and photo library using Telegram's Topics (forum threads) as categories.

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
| `GROUP_CHAT_ID` | ✅ | Telegram Chat ID of the managed group |
| `GENERAL_TOPIC_THREAD_ID` | ✅ | Thread ID of the General topic (usually 1) |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `WEBHOOK_BASE_URL` | ✅ | Public URL of this service |
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
│   ├── scheduler/                 # APScheduler setup and jobs
│   ├── backup/                    # JSON export/import
│   └── audit/                     # Central audit logging
└── tests/
    ├── unit/                      # Unit tests for services/
    └── integration/               # Integration tests (real Telegram group)
```
