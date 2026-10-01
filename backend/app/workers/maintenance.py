"""Operator maintenance: find (and optionally remove) orphaned stored media.

Storage layout: lectures/{user_id}/{lecture_id}/{original|processed}/{file}. An object is
an orphan only when it is *safely identifiable* as one:

  * its lecture no longer exists (e.g. the lecture was deleted while a worker was still
    uploading its playback audio, so the upload landed after the cleanup), or
  * its lecture exists but no lecture_media row references the object (e.g. derived
    audio stored by an earlier version), or
  * its user folder doesn't match the lecture's owner (never written by the app),

and, in every case, it is older than --min-age-hours, so an upload that is about to be
recorded by a running worker is never touched. Nothing is deleted unless --apply is
given; the default is a dry run that lists what would be removed.

    python -m app.workers.maintenance orphans            # dry run
    python -m app.workers.maintenance orphans --apply    # delete the listed objects
"""

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings
from app.services.ingestion import BUCKET
from app.services.supabase_admin import ServiceSupabase


@dataclass(frozen=True)
class Orphan:
    path: str
    reason: str
    size: int | None
    created_at: str | None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _walk(admin: ServiceSupabase, prefix: str, depth: int = 0) -> list[tuple[str, dict]]:
    files: list[tuple[str, dict]] = []
    for entry in await admin.list_objects(BUCKET, prefix):
        path = f"{prefix}{entry['name']}"
        if entry.get("id"):
            files.append((path, entry))
        elif depth < 3:
            files.extend(await _walk(admin, f"{path}/", depth + 1))
    return files


def classify(
    path: str, entry: dict, lectures: dict[str, str], referenced: set[str], *, cutoff: datetime
) -> Orphan | None:
    """The reason `path` is an orphan, or None when it must be kept."""
    created = _parse_time(entry.get("created_at"))
    if created is None or created > cutoff:
        return None  # unknown or recent: could belong to an upload in progress
    parts = path.split("/")
    if len(parts) < 3:
        reason = "unexpected_location"
    elif parts[1] not in lectures:
        reason = "lecture_missing"
    elif lectures[parts[1]] != parts[0]:
        reason = "owner_mismatch"
    elif path not in referenced:
        reason = "unreferenced"
    else:
        return None
    size = (entry.get("metadata") or {}).get("size")
    return Orphan(path=path, reason=reason, size=size, created_at=entry.get("created_at"))


async def find_orphans(admin: ServiceSupabase, *, min_age_hours: float) -> list[Orphan]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    lectures = {row["id"]: row["user_id"] for row in await admin.select_all("lectures", {"select": "id,user_id", "order": "id"})}
    referenced = {row["storage_path"] for row in await admin.select_all("lecture_media", {"select": "storage_path", "order": "id"})}
    orphans = []
    for path, entry in await _walk(admin, ""):
        orphan = classify(path, entry, lectures, referenced, cutoff=cutoff)
        if orphan:
            orphans.append(orphan)
    return orphans


async def main(apply: bool, min_age_hours: float) -> None:
    settings = get_settings()
    if not settings.ingestion_configured:
        raise SystemExit("SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY must be set.")
    async with httpx.AsyncClient(timeout=60) as http:
        admin = ServiceSupabase(http, settings)
        orphans = await find_orphans(admin, min_age_hours=min_age_hours)
        print(json.dumps({"apply": apply, "min_age_hours": min_age_hours, "orphans": [asdict(o) for o in orphans]}, indent=2))
        if apply and orphans:
            paths = [o.path for o in orphans]
            for start in range(0, len(paths), 100):
                await admin.remove_objects(BUCKET, paths[start : start + 100])
            print(f"Removed {len(paths)} orphaned object(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    orphans_cmd = sub.add_parser("orphans", help="find orphaned stored media (dry run unless --apply)")
    orphans_cmd.add_argument("--apply", action="store_true", help="delete the orphans that were found")
    orphans_cmd.add_argument("--min-age-hours", type=float, default=24.0, help="ignore objects newer than this")
    args = parser.parse_args()
    asyncio.run(main(args.apply, args.min_age_hours))
