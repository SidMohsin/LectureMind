import uuid
from datetime import date, datetime

from pydantic import BaseModel


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
    created_at: datetime
    updated_at: datetime


class LectureList(BaseModel):
    items: list[Lecture]
    total: int
    limit: int
    offset: int


class SubjectList(BaseModel):
    subjects: list[str]
