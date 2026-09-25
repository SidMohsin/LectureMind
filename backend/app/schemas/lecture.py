"""
Pydantic request/response schemas for the LectureMind API.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class LectureUploadResponse(BaseModel):
    lecture_id: str
    original_filename: str
    file_type: str
    status: str
    message: str


class LectureStatusResponse(BaseModel):
    lecture_id: str
    status: str
    status_message: Optional[str] = None
    error_message: Optional[str] = None
    num_chunks: int = 0


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    lecture_id: str
    language: Optional[str] = None
    segments: List[TranscriptSegment]
    full_text: str


class SummaryResponse(BaseModel):
    lecture_id: str
    overview: str
    main_concepts: List[str]
    important_points: List[str]
    key_takeaways: List[str]


class KeywordsResponse(BaseModel):
    lecture_id: str
    keywords: List[str]


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: Optional[int] = None


class SourceChunk(BaseModel):
    chunk_id: str
    text: str
    start: float
    end: float
    score: float


class ChatResponse(BaseModel):
    lecture_id: str
    question: str
    answer: str
    grounded: bool
    sources: List[SourceChunk]
    latency_ms: float

class ChatHistoryItem(BaseModel):
    id: int
    lecture_id: str
    question: str
    answer: str
    sources: List[SourceChunk] = []
    latency_ms: float
    created_at: str


class ChatHistoryResponse(BaseModel):
    lecture_id: str
    items: List[ChatHistoryItem]

class LectureListItem(BaseModel):
    lecture_id: str
    original_filename: str
    file_type: str
    status: str
    upload_time: str
    duration_seconds: Optional[float] = None
    num_chunks: int = 0
    question_count: int = 0


class LectureListResponse(BaseModel):
    lectures: List[LectureListItem]


class LectureSearchResult(BaseModel):
    lecture_id: str
    original_filename: str
    match_type: str
    text: str
    start: Optional[float] = None
    end: Optional[float] = None


class LectureSearchResponse(BaseModel):
    results: List[LectureSearchResult]


class LectureDetailResponse(BaseModel):
    """Full metadata for a single lecture — used by the lecture workspace page."""
    lecture_id: str
    original_filename: str
    file_type: str
    status: str
    status_message: Optional[str] = None
    error_message: Optional[str] = None
    upload_time: str
    duration_seconds: Optional[float] = None
    num_chunks: int = 0
    has_media: bool = False
    processing_started_at: Optional[str] = None
    processing_completed_at: Optional[str] = None


class StatsResponse(BaseModel):
    """Aggregate stats derived from real lecture/chat data — never fabricated."""
    total_lectures: int
    completed_lectures: int
    processing_lectures: int
    failed_lectures: int
    total_duration_seconds: float
    total_questions_asked: int


class ConfigResponse(BaseModel):
    """Non-secret configuration values, safe to display in the Settings page."""
    llm_provider: str
    llm_model: str
    embedding_model: str
    whisper_model_size: str
    whisper_device: str
    top_k: int
    chunk_size_words: int
    chunk_overlap_words: int


class DeleteResponse(BaseModel):
    lecture_id: str
    deleted: bool
    message: str
