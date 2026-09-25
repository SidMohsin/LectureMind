"""
SQLAlchemy ORM model for the User table.
"""
import uuid
import datetime as dt
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text
from app.database import Base


def gen_user_id() -> str:
    return uuid.uuid4().hex[:16]


class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, default=gen_user_id)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class OTP(Base):
    """One-time passwords for account verification and password reset."""
    __tablename__ = "otps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    otp_hash = Column(String(255), nullable=False)
    purpose = Column(String(30), nullable=False)  # "signup" | "password_reset"
    method = Column(String(10), nullable=False)    # "email" | "phone"
    attempts = Column(Integer, default=0)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class PasswordResetToken(Base):
    """Tracks password reset flow state."""
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    token_hash = Column(String(255), nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
