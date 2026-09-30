import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator

TITLE_MAX, SUBJECT_MAX, TOPIC_MAX, INSTRUCTOR_MAX = 300, 120, 200, 120
MAX_TAGS, TAG_MAX = 20, 40


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def clean_tags(values: list[str]) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for raw in values:
        tag = raw.strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise ValueError(f"Use at most {MAX_TAGS} tags.")
    if any(len(tag) > TAG_MAX for tag in tags):
        raise ValueError(f"Keep each tag under {TAG_MAX} characters.")
    return tags


class LectureMetadataIn(BaseModel):
    title: str | None = Field(default=None, max_length=TITLE_MAX)
    subject: str = Field(max_length=SUBJECT_MAX)
    topic: str | None = Field(default=None, max_length=TOPIC_MAX)
    instructor: str | None = Field(default=None, max_length=INSTRUCTOR_MAX)
    lecture_date: date | None = None
    tags: list[str] = Field(default_factory=list)

    _optional = field_validator("title", "topic", "instructor", mode="after")(_clean_optional)

    @field_validator("subject", mode="after")
    @classmethod
    def _subject(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter the subject or discipline.")
        return value

    @field_validator("tags", mode="after")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return clean_tags(value)


class SourceSubmission(LectureMetadataIn):
    url: HttpUrl
    rights_confirmed: bool


class JobSummary(BaseModel):
    id: uuid.UUID
    status: str
    current_stage: str
    attempt_count: int
    max_attempts: int
    error_code: str | None
    error_message: str | None
    retryable: bool | None
    status_detail: str | None
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    failed_at: datetime | None
    next_attempt_at: datetime | None
    updated_at: datetime


class IngestedLecture(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    source_type: str
    source_url: str | None


class IngestionResult(BaseModel):
    lecture: IngestedLecture
    job: JobSummary | None
    replayed: bool


class KindLimits(BaseModel):
    max_bytes: int
    formats: list[str]


class IngestionLimits(BaseModel):
    video: KindLimits
    audio: KindLimits
    max_duration_seconds: int
    source_urls_enabled: bool
    source_providers: list[str]


class StageRun(BaseModel):
    stage: str
    attempt: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_code: str | None


class MediaRecord(BaseModel):
    kind: str
    mime_type: str
    file_size: int
    duration_seconds: float | None
    probe: dict


class ProcessingDetails(BaseModel):
    lecture: IngestedLecture
    job: JobSummary | None
    stage_runs: list[StageRun]
    media: list[MediaRecord]
    implemented_stages: list[str]
