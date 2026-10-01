import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.workspace import Source


class LectureRef(BaseModel):
    id: uuid.UUID
    title: str
    subject: str | None = None
    topic: str | None = None
    instructor: str | None = None
    lecture_date: date | None = None


class ContentResult(BaseModel):
    chunk_id: uuid.UUID
    lecture: LectureRef
    sequence: int
    start_seconds: float
    end_seconds: float
    text: str
    similarity: float


class ContentSearch(BaseModel):
    query: str
    results: list[ContentResult]
    min_similarity: float
    embedding_model: str
    latency_ms: int


class HistoryEntry(BaseModel):
    id: uuid.UUID
    lecture: LectureRef
    question: str
    outcome: Literal["answered", "insufficient_evidence"]
    answer: str
    sources: list[Source]
    latency_ms: int
    created_at: datetime


class HistoryPage(BaseModel):
    items: list[HistoryEntry]
    total: int
    limit: int
    offset: int
