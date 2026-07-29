from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.config import config

Base = declarative_base()

class MediaItem(Base):
    __tablename__ = 'media_items'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(255), unique=True)
    file_type = Column(String(50))
    caption = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
