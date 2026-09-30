from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.services.supabase_admin import ServiceSupabase
from app.workers.lifecycle import LeaseLost
from app.workers.media import ProbeResult


@dataclass
class AudioArtifact:
    """Normalized audio for transcription. Lives only in the job's temporary workspace."""

    path: Path
    duration_seconds: float
    checksum_sha256: str
    probe: ProbeResult
    details: dict
    input_probe: ProbeResult
    original_media: dict | None  # the stored original's lecture_media row (None for source URLs)


@dataclass
class JobContext:
    admin: ServiceSupabase
    settings: Settings
    worker_id: str
    job: dict
    lecture: dict
    workspace: Path
    # Set by stages.prepare_audio(); reused by later stages in the same run.
    audio: AudioArtifact | None = None

    @property
    def job_id(self) -> str:
        return self.job["id"]

    async def ensure_active(self) -> None:
        """Renew the lease; raises LeaseLost if the job was taken over or its lecture deleted."""
        renewed = await self.admin.rpc(
            "renew_processing_lease",
            {"p_job_id": self.job_id, "p_worker": self.worker_id, "p_lease_seconds": self.settings.worker_lease_seconds},
        )
        if renewed is not True:
            raise LeaseLost()
