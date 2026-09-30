"""Private, per-job scratch directories for downloads and FFmpeg output.

Each job run gets a fresh directory that is always removed when the run ends,
whether it succeeded or failed. Directories left behind by a crashed worker are
removed at worker start-up once they are older than the stale threshold.
"""

import logging
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

PREFIX = "job-"


@contextmanager
def job_workspace(root: Path, job_id: str):
    root.mkdir(parents=True, exist_ok=True)
    # A fresh random suffix per run: two runs of the same job never share files.
    path = root / f"{PREFIX}{uuid.UUID(job_id).hex}-{uuid.uuid4().hex[:8]}"
    path.mkdir(mode=0o700)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def remove_stale_workspaces(root: Path, older_than_seconds: float) -> int:
    if not root.exists():
        return 0
    cutoff = time.time() - older_than_seconds
    removed = 0
    for entry in root.iterdir():
        if entry.is_dir() and entry.name.startswith(PREFIX) and entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    if removed:
        logger.info("Removed %d stale job workspace(s) from %s", removed, os.fspath(root))
    return removed
