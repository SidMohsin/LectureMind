import uuid
from typing import Literal

from app.services.supabase_rest import UserScopedSupabase

MEDIA_BUCKET = "lectures"

LECTURE_COLUMNS = (
    "id,title,subject,topic,instructor,lecture_date,tags,source_type,source_url,"
    "status,duration_seconds,created_at,updated_at"
)

StatusGroup = Literal["ready", "processing", "failed"]
SourceType = Literal["video", "audio", "url"]
SortOrder = Literal["newest", "oldest", "title", "duration"]

_STATUS_FILTERS: dict[str, str] = {
    "ready": "eq.READY",
    "failed": "eq.FAILED",
    "processing": "not.in.(READY,FAILED)",
}

_SORTS: dict[str, str] = {
    "newest": "created_at.desc,id.desc",
    "oldest": "created_at.asc,id.asc",
    "title": "title.asc,created_at.desc",
    "duration": "duration_seconds.desc.nullslast,created_at.desc",
}


def search_pattern(query: str) -> str:
    """ILIKE pattern for a user's search text; wildcard characters match literally."""
    escaped = query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("*", "")
    return f"*{escaped}*"


async def list_lectures(
    db: UserScopedSupabase,
    user_id: uuid.UUID,
    *,
    query: str | None,
    subject: str | None,
    status_group: StatusGroup | None,
    source_type: SourceType | None,
    sort: SortOrder,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    params = {
        "select": LECTURE_COLUMNS,
        "user_id": f"eq.{user_id}",
        "order": _SORTS[sort],
        "limit": str(limit),
        "offset": str(offset),
    }
    if query and query.strip():
        params["search_text"] = f"ilike.{search_pattern(query)}"
    if subject:
        params["subject"] = f"eq.{subject}"
    if status_group:
        params["status"] = _STATUS_FILTERS[status_group]
    if source_type:
        params["source_type"] = f"eq.{source_type}"
    return await db.select_counted("lectures", params)


async def list_subjects(db: UserScopedSupabase, user_id: uuid.UUID) -> list[str]:
    rows = await db.select(
        "lectures",
        {"select": "subject", "user_id": f"eq.{user_id}", "subject": "not.is.null", "order": "subject.asc"},
    )
    return sorted({row["subject"] for row in rows if row["subject"].strip()}, key=str.casefold)


async def get_lecture(db: UserScopedSupabase, user_id: uuid.UUID, lecture_id: uuid.UUID) -> dict | None:
    rows = await db.select(
        "lectures", {"select": LECTURE_COLUMNS, "id": f"eq.{lecture_id}", "user_id": f"eq.{user_id}"}
    )
    return rows[0] if rows else None


async def _collect_media_paths(db: UserScopedSupabase, prefix: str, depth: int = 0) -> list[str]:
    paths: list[str] = []
    for entry in await db.list_objects(MEDIA_BUCKET, prefix):
        path = f"{prefix}{entry['name']}"
        if entry.get("id"):
            paths.append(path)
        elif depth < 3:  # folder placeholder: original/, processed/, derived/
            paths.extend(await _collect_media_paths(db, f"{path}/", depth + 1))
    return paths


async def delete_lecture(db: UserScopedSupabase, user_id: uuid.UUID, lecture_id: uuid.UUID) -> bool:
    """Delete a lecture and its stored media. Returns False if the caller doesn't own it.

    Media goes first: storage policies only allow access while the owning lecture
    row exists, and a failure here leaves the lecture intact so the user can retry.
    """
    if await get_lecture(db, user_id, lecture_id) is None:
        return False

    media = await _collect_media_paths(db, f"{user_id}/{lecture_id}/")
    if media:
        await db.remove_objects(MEDIA_BUCKET, media)

    deleted = await db.delete("lectures", {"id": f"eq.{lecture_id}", "user_id": f"eq.{user_id}"})
    return len(deleted) == 1
