"""In-memory stand-ins for Supabase (service role) and the Redis queue.

FakeAdmin implements the subset of PostgREST filtering the code uses (eq./in./
not.in./is.null) plus the three worker RPCs with the same semantics as the SQL
functions in supabase/migrations, so pipeline logic is tested without network.
"""

import asyncio
import copy
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.supabase_admin import ConflictError, StorageObjectTooLarge

UNIQUE = {
    "lectures": [("user_id", "client_request_id"), ("user_id", "source_fingerprint")],
    "processing_jobs": [("lecture_id",)],
    "lecture_media": [("lecture_id", "kind")],
    "processing_stage_runs": [("job_id", "stage", "attempt")],
    "transcripts": [("lecture_id",)],
    "transcript_segments": [("lecture_id", "sequence")],
    "lecture_chunks": [("id",), ("lecture_id", "sequence")],
    "chapters": [("lecture_id", "sequence")],
    "lecture_intelligence": [("lecture_id",)],
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _matches(row: dict, filters: dict[str, str]) -> bool:
    for column, expression in filters.items():
        if column in ("select", "order", "limit", "offset", "on_conflict"):
            continue
        value = row.get(column)
        if expression.startswith("eq."):
            if str(value) != expression[3:] and not (isinstance(value, bool) and str(value).lower() == expression[3:]):
                return False
        elif expression.startswith("in.("):
            if str(value) not in expression[4:-1].split(","):
                return False
        elif expression.startswith("not.in.("):
            if str(value) in expression[8:-1].split(","):
                return False
        elif expression == "is.null":
            if value is not None:
                return False
        elif expression.startswith(("lt.", "gt.")):
            # Timestamps compare as instants; a NULL never matches (as in PostgREST).
            if value is None:
                return False
            left, right = _ts(value), _ts(expression[3:])
            if (left >= right) if expression.startswith("lt.") else (left <= right):
                return False
        else:
            raise NotImplementedError(expression)
    return True


class FakeAdmin:
    def __init__(self, storage_dir: Path | None = None):
        self.tables: dict[str, list[dict]] = {name: [] for name in UNIQUE}
        self.storage: dict[str, bytes] = {}
        self.calls: list[tuple] = []
        self.fail_upload: Exception | None = None
        self.fail_download: Exception | None = None
        self.storage_dir = storage_dir
        self.lease_valid = True  # set False to simulate a lost lease / deleted lecture

    # --- helpers for tests ---
    def rows(self, table: str, **filters) -> list[dict]:
        return [row for row in self.tables[table] if all(str(row.get(k)) == str(v) for k, v in filters.items())]

    def add(self, table: str, **row) -> dict:
        row.setdefault("id", str(uuid.uuid4()))
        self.tables[table].append(row)
        return row

    # --- database ---
    async def select(self, table, params):
        self.calls.append(("select", table, dict(params)))
        return [copy.deepcopy(row) for row in self.tables[table] if _matches(row, params)]

    async def insert(self, table, row, *, on_conflict=None):
        self.calls.append(("insert", table, dict(row)))
        row = {"id": str(uuid.uuid4()), **copy.deepcopy(row)}
        defaults = {
            "lectures": {
                "status": "UPLOADED", "duration_seconds": None, "created_at": now().isoformat(),
                "updated_at": now().isoformat(), "tags": [], "subject": None, "topic": None, "instructor": None,
                "lecture_date": None, "source_url": None, "original_filename": None, "source_fingerprint": None,
                "client_request_id": None, "source_rights_confirmed_at": None,
            },
            "processing_jobs": {
                "status": "queued", "current_stage": "EXTRACTING_AUDIO", "attempt_count": 0, "max_attempts": 3,
                "next_attempt_at": now().isoformat(), "lease_owner": None, "lease_expires_at": None,
                "error_code": None, "error_message": None, "retryable": None, "status_detail": None,
                "queued_at": now().isoformat(), "started_at": None, "finished_at": None, "failed_at": None,
                "updated_at": now().isoformat(),
            },
            "processing_stage_runs": {"status": "running", "started_at": now().isoformat()},
            "lecture_media": {"probe": {}},
            "lecture_chunks": {"embedding": None, "embedding_model": None},
        }.get(table, {})
        if table in ("transcripts", "transcript_segments", "chapters", "lecture_intelligence"):
            row.pop("id", None)  # these tables are keyed by lecture (+ sequence), not by id
        row = {**defaults, **row}
        for keys in UNIQUE[table]:
            if any(row.get(k) is None for k in keys):
                continue
            clash = next((r for r in self.tables[table] if all(r.get(k) == row.get(k) for k in keys)), None)
            if clash:
                if on_conflict and tuple(on_conflict.split(",")) == keys:
                    clash.update({k: v for k, v in row.items() if k != "id"})
                    return copy.deepcopy(clash)
                raise ConflictError(f"duplicate {keys}")
        self.tables[table].append(row)
        return copy.deepcopy(row)

    async def insert_many(self, table, rows, *, on_conflict=None, batch=500):
        self.calls.append(("insert_many", table, len(rows)))
        for row in rows:
            await self.insert(table, row, on_conflict=on_conflict)

    async def select_all(self, table, params, *, page=1000):
        rows = await self.select(table, params)
        order = params.get("order", "")
        if order:
            column, _, direction = order.split(",")[0].partition(".")
            rows.sort(key=lambda r: r.get(column), reverse=direction.startswith("desc"))
        return rows

    async def update(self, table, filters, values):
        self.calls.append(("update", table, dict(filters), dict(values)))
        updated = []
        for row in self.tables[table]:
            if _matches(row, filters):
                row.update(copy.deepcopy(values))
                updated.append(copy.deepcopy(row))
        return updated

    async def delete(self, table, filters):
        self.calls.append(("delete", table, dict(filters)))
        doomed = [row for row in self.tables[table] if _matches(row, filters)]
        for row in doomed:
            self.tables[table].remove(row)
            if table == "lectures":  # ON DELETE CASCADE
                for child in ("processing_jobs", "lecture_media"):
                    self.tables[child] = [r for r in self.tables[child] if r["lecture_id"] != row["id"]]

    async def rpc(self, function, args):
        self.calls.append(("rpc", function, dict(args)))
        jobs = self.tables["processing_jobs"]
        if function == "claim_processing_job":
            for job in jobs:
                if job["id"] == args["p_job_id"] and job["status"] == "queued" and _ts(job["next_attempt_at"]) <= now():
                    job.update(
                        status="running",
                        lease_owner=args["p_worker"],
                        lease_expires_at=(now() + timedelta(seconds=args["p_lease_seconds"])).isoformat(),
                        attempt_count=job["attempt_count"] + 1,
                        started_at=job["started_at"] or now().isoformat(),
                        status_detail=None,
                    )
                    return [copy.deepcopy(job)]
            return []
        if function == "renew_processing_lease":
            job = next((j for j in jobs if j["id"] == args["p_job_id"]), None)
            return bool(self.lease_valid and job and job["status"] == "running" and job["lease_owner"] == args["p_worker"])
        if function == "recover_processing_jobs":
            for job in jobs:
                if job["status"] == "running" and _ts(job["lease_expires_at"]) < now():
                    if job["attempt_count"] >= job["max_attempts"]:
                        job.update(status="failed", lease_owner=None, lease_expires_at=None, error_code="processing_interrupted",
                                   retryable=True, failed_at=now().isoformat(), finished_at=now().isoformat())
                        for lecture in self.tables["lectures"]:
                            if lecture["id"] == job["lecture_id"] and lecture["status"] not in ("READY", "FAILED"):
                                lecture["status"] = "FAILED"
                    else:
                        job.update(status="queued", lease_owner=None, lease_expires_at=None)
            due = [j for j in jobs if j["status"] == "queued" and _ts(j["next_attempt_at"]) <= now()]
            return [{"job_id": j["id"]} for j in due][: args.get("p_limit", 50)]
        raise NotImplementedError(function)

    # --- storage ---
    async def upload_file(self, bucket, path, source, content_type, *, upsert):
        self.calls.append(("upload", bucket, path, content_type, upsert))
        if self.fail_upload:
            raise self.fail_upload
        key = f"{bucket}/{path}"
        if key in self.storage and not upsert:
            raise ConflictError("exists")
        self.storage[key] = Path(source).read_bytes()

    async def download_file(self, bucket, path, destination, max_bytes):
        self.calls.append(("download", bucket, path))
        if self.fail_download:
            raise self.fail_download
        data = self.storage[f"{bucket}/{path}"]
        if len(data) > max_bytes:
            raise StorageObjectTooLarge()
        Path(destination).write_bytes(data)
        return len(data)

    async def object_exists(self, bucket, path):
        return f"{bucket}/{path}" in self.storage

    async def remove_objects(self, bucket, paths):
        self.calls.append(("remove", bucket, list(paths)))
        for path in paths:
            self.storage.pop(f"{bucket}/{path}", None)


class FakeQueue:
    def __init__(self, fail: bool = False):
        self.items: list[str] = []
        self.fail = fail
        self.workers: dict[str, dict] = {}

    async def enqueue(self, job_id, *, dedupe_seconds=0):
        if self.fail:
            raise ConnectionError("redis down")
        self.items.insert(0, job_id)

    async def dequeue(self, timeout_seconds):
        if self.fail:
            raise ConnectionError("redis down")
        if not self.items:
            await asyncio.sleep(0.01)  # like BRPOP timing out, without a busy loop
            return None
        return self.items.pop()

    async def ping(self):
        return not self.fail

    async def announce_worker(self, worker_id, info, ttl_seconds):
        if self.fail:
            raise ConnectionError("redis down")
        self.workers[worker_id] = info

    async def active_workers(self):
        if self.fail:
            raise ConnectionError("redis down")
        return list(self.workers.values())

    async def close(self):
        pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
