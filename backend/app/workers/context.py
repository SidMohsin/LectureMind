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
    source_path: Path | None = None  # the acquired source, when kept for further use in this stage


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

    async def report(self, detail: str) -> None:
        """Show measurable progress on the job (e.g. minutes of audio transcribed)."""
        rows = await self.admin.update(
            "processing_jobs",
            {"id": f"eq.{self.job_id}", "status": "eq.running", "lease_owner": f"eq.{self.worker_id}"},
            {"status_detail": detail[:300]},
        )
        if not rows:
            raise LeaseLost()

    async def ensure_active(self) -> None:
        """Renew the lease; raises LeaseLost if the job was taken over or its lecture deleted."""
        renewed = await self.admin.rpc(
            "renew_processing_lease",
            {"p_job_id": self.job_id, "p_worker": self.worker_id, "p_lease_seconds": self.settings.worker_lease_seconds},
        )
        if renewed is not True:
            raise LeaseLost()
