import os
from dotenv import load_dotenv

load_dotenv()

def _require(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"[STARTUP ERROR] Required environment variable '{name}' is missing or empty.")
    return value

class Config:
    def __init__(self):
        self.TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
        self.OWNER_TELEGRAM_ID = int(_require("OWNER_TELEGRAM_ID"))
        self.WEBHOOK_SECRET_TOKEN = _require("WEBHOOK_SECRET_TOKEN")
        self.GROUP_CHAT_ID = int(_require("GROUP_CHAT_ID"))
        self.GENERAL_TOPIC_THREAD_ID = int(os.getenv("GENERAL_TOPIC_THREAD_ID", 1))
        self.DATABASE_URL = _require("DATABASE_URL")
        self.WEBHOOK_BASE_URL = _require("WEBHOOK_BASE_URL")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

config = Config()
