"""
SQLAlchemy ORM models for LectureMind.
"""
import uuid
import datetime as dt
from sqlalchemy import Column, String, DateTime, Float, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:16]


class Lecture(Base):
    __tablename__ = "lectures"

    lecture_id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # video | audio
    upload_time = Column(DateTime, default=dt.datetime.utcnow)
    duration_seconds = Column(Float, nullable=True)

    status = Column(String, default="uploaded")
    # uploaded -> extracting_audio -> transcribing -> cleaning ->
    # chunking -> embedding -> indexing -> summarizing -> extracting_keywords -> completed | failed
    status_message = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    audio_path = Column(String, nullable=True)
    transcript_path = Column(String, nullable=True)
    raw_media_path = Column(String, nullable=True)

    summary_json = Column(Text, nullable=True)
    keywords_json = Column(Text, nullable=True)

    num_chunks = Column(Integer, default=0)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)

    # Relationships
    chat_logs = relationship("ChatLog", back_populates="lecture", cascade="all, delete-orphan")
    owner = relationship("User", backref="lectures")


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(String, ForeignKey("lectures.lecture_id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    question = Column(Text)
    answer = Column(Text)
    sources_json = Column(Text)
    latency_ms = Column(Float)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # Relationships
    lecture = relationship("Lecture", back_populates="chat_logs")
