import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.lectures import Lecture


class TranscriptSegment(BaseModel):
    sequence: int
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    language: str | None
    model: str | None
    segments: list[TranscriptSegment]


class Chapter(BaseModel):
    sequence: int
    title: str
    description: str | None
    start_seconds: float
    end_seconds: float
    first_chunk: int
    last_chunk: int


class ChunkTime(BaseModel):
    sequence: int
    start: float
    end: float


class Intelligence(BaseModel):
    summary: str
    topics: list[dict]
    key_concepts: list[dict]
    definitions: list[dict]
    keywords: list[str]
    important_points: list[dict]
    examples: list[dict]
    model: str | None
    prompt_version: str | None
    created_at: datetime | None = None


class Workspace(BaseModel):
    lecture: Lecture
    transcript: Transcript | None
    chapters: list[Chapter]
    intelligence: Intelligence | None
    # Start/end time of every chunk, so chunk citations in the intelligence map to timestamps.
    chunks: list[ChunkTime]


class MediaAccess(BaseModel):
    kind: Literal["video", "audio"]
    mime_type: str
    url: str
    expires_in: int
    duration_seconds: float | None


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)

    @field_validator("question")
    @classmethod
    def _meaningful(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("Ask a question of at least 3 characters.")
        return value


class Source(BaseModel):
    number: int
    chunk_id: str
    sequence: int
    start_seconds: float
    end_seconds: float
    similarity: float
    text: str
    cited: bool


class QuestionAnswer(BaseModel):
    id: uuid.UUID
    question: str
    outcome: Literal["answered", "insufficient_evidence"]
    answer: str
    sources: list[Source]
    latency_ms: int
    created_at: datetime


class QuestionHistory(BaseModel):
    items: list[QuestionAnswer]
