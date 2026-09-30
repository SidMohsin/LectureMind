"""The lecture processing lifecycle (Architecture §10) and its transition rules.

Phase boundary: Phase 4 implements EXTRACTING_AUDIO. Later stages
(TRANSCRIBING … GENERATING_INTELLIGENCE) are registered by Phase 5. When the
pipeline reaches a stage that has no implementation yet, the job waits there
(job status "waiting"); it is never marked READY and no stage output is faked.
"""

from dataclasses import dataclass, field

# Lecture.status values in order.
LECTURE_STATUSES = (
    "UPLOADED",
    "QUEUED",
    "EXTRACTING_AUDIO",
    "TRANSCRIBING",
    "CLEANING",
    "CHUNKING",
    "EMBEDDING",
    "INDEXING",
    "GENERATING_INTELLIGENCE",
    "READY",
)
FAILED = "FAILED"

# The stages a worker executes (processing_jobs.current_stage).
PIPELINE_STAGES = LECTURE_STATUSES[2:9]

JOB_STATUSES = ("queued", "running", "waiting", "succeeded", "failed")

_JOB_TRANSITIONS = {
    "queued": {"running"},
    # running -> queued: automatic retry, or recovery after a lost worker.
    "running": {"queued", "waiting", "succeeded", "failed"},
    # waiting -> queued: the missing stage has been implemented.
    "waiting": {"queued"},
    # failed -> queued: user retry.
    "failed": {"queued"},
    "succeeded": set(),
}


def next_stage(stage: str) -> str | None:
    """The stage after `stage`, or None when `stage` is the last one (lecture becomes READY)."""
    index = PIPELINE_STAGES.index(stage)
    return PIPELINE_STAGES[index + 1] if index + 1 < len(PIPELINE_STAGES) else None


def can_transition_lecture(current: str, target: str) -> bool:
    if current == target:
        return False
    if target == FAILED:
        return current not in ("READY", FAILED)
    if target == "QUEUED":
        # First enqueue, a retry after failure, or re-queueing a stage for another attempt.
        return current == "UPLOADED" or current == FAILED or current in PIPELINE_STAGES
    if current == "QUEUED":
        return target in PIPELINE_STAGES
    if current in PIPELINE_STAGES:
        position = LECTURE_STATUSES.index(current)
        return target == LECTURE_STATUSES[position + 1]
    return False


def can_transition_job(current: str, target: str) -> bool:
    return target in _JOB_TRANSITIONS.get(current, set())


class InvalidTransition(Exception):
    pass


def require_lecture_transition(current: str, target: str) -> None:
    if not can_transition_lecture(current, target):
        raise InvalidTransition(f"Lecture cannot move from {current} to {target}.")


def require_job_transition(current: str, target: str) -> None:
    if not can_transition_job(current, target):
        raise InvalidTransition(f"Job cannot move from {current} to {target}.")


@dataclass
class ProcessingError(Exception):
    """A stage failure. `message` is shown to the user; `details` stays server-side."""

    code: str
    message: str
    retryable: bool = False
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        super().__init__(self.message)


class LeaseLost(Exception):
    """Another worker took the job over (or the lecture was deleted); stop without writing."""
