"""
SQLite database setup using SQLAlchemy.
Stores lecture metadata, processing status, results, and user/auth data.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Import all models so their tables are registered with Base.metadata
    from app.models import User, OTP, PasswordResetToken, Lecture, ChatLog  # noqa: F401
    Base.metadata.create_all(bind=engine)
