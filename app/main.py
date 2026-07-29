import uvicorn
from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from app.config import config
from app.database import init_db
from app.handlers import start, handle_media
import asyncio

app = FastAPI()

# Telegram Bot Application
tg_app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))

@app.on_event("startup")
async def startup():
    init_db()
    await tg_app.initialize()
    webhook_url = f"{config.WEBHOOK_BASE_URL}/webhook"
    await tg_app.bot.set_webhook(url=webhook_url, secret_token=config.WEBHOOK_SECRET_TOKEN)
    print(f"Webhook set to {webhook_url}")

@app.on_event("shutdown")
async def shutdown():
    await tg_app.shutdown()

@app.post("/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(None)):
    if x_telegram_bot_api_secret_token != config.WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Telegram Media Manager is running"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=10000, reload=True)
