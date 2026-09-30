import uuid
from datetime import date, datetime

from pydantic import BaseModel


class LectureJob(BaseModel):
    status: str
    current_stage: str
    error_code: str | None
    error_message: str | None
    retryable: bool | None
    status_detail: str | None
    attempt_count: int
    updated_at: datetime


class Lecture(BaseModel):
    id: uuid.UUID
    title: str
    subject: str | None
    topic: str | None
    instructor: str | None
    lecture_date: date | None
    tags: list[str]
    source_type: str
    source_url: str | None
    status: str
    duration_seconds: int | None
    original_filename: str | None = None
    created_at: datetime
    updated_at: datetime
    job: LectureJob | None = None


class LectureList(BaseModel):
    items: list[Lecture]
    total: int
    limit: int
    offset: int


class SubjectList(BaseModel):
    subjects: list[str]
