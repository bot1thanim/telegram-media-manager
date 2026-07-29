from telegram import Update
from telegram.ext import ContextTypes
from app.database import SessionLocal, MediaItem
from app.config import config

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("שלום! אני בוט ניהול המדיה שלך. שלח לי תמונה או וידאו כדי לשמור.")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    file_id = None
    file_type = None
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = 'photo'
    elif message.video:
        file_id = message.video.file_id
        file_type = 'video'
    
    if file_id:
        db = SessionLocal()
        new_item = MediaItem(telegram_id=file_id, file_type=file_type, caption=message.caption)
        db.add(new_item)
        db.commit()
        db.close()
        await message.reply_text(f"המדיה מסוג {file_type} נשמרה בהצלחה ב-Supabase!")
