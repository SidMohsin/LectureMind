"""Question history across the caller's lectures, and deleting questions.

Reads go through the user-scoped client (RLS: own rows, for lectures they still own) and
always filter by the caller's id as well. Deletes are performed by the server after the
ownership check, filtered by both the question/lecture id and the caller's id; clients
still have no write access to chat_logs.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_current_user, get_user_db
from app.api.workspace import get_admin
from app.core.security import AuthenticatedUser
from app.repositories.lectures import search_pattern
from app.schemas.search import HistoryPage
from app.services.supabase_admin import ServiceSupabase
from app.services.supabase_rest import UserScopedSupabase

router = APIRouter(prefix="/questions", tags=["history"])

HISTORY_FIELDS = (
    "id,question,outcome,answer,sources,latency_ms,created_at,"
    "lecture:lectures(id,title,subject,topic,instructor,lecture_date)"
)
ORDERS = {"newest": "created_at.desc,id.desc", "oldest": "created_at.asc,id.asc"}


def _quoted(value: str) -> str:
    """A PostgREST filter value that may contain commas, parentheses or quotes."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@router.get("", response_model=HistoryPage)
async def list_history(
    q: str | None = Query(default=None, max_length=200),
    lecture_id: uuid.UUID | None = None,
    order: Literal["newest", "oldest"] = "newest",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    params = {
        "select": HISTORY_FIELDS,
        "user_id": f"eq.{user.id}",
        "order": ORDERS[order],
        "limit": str(limit),
        "offset": str(offset),
    }
    if lecture_id:
        params["lecture_id"] = f"eq.{lecture_id}"
    if q and q.strip():
        pattern = _quoted(search_pattern(q))
        params["or"] = f"(question.ilike.{pattern},answer.ilike.{pattern})"
    rows, total = await db.select_counted("chat_logs", params)
    # A row whose lecture isn't readable can't be shown with its context (RLS hides such rows anyway).
    return {"items": [row for row in rows if row.get("lecture")], "total": total, "limit": limit, "offset": offset}


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
    admin: ServiceSupabase = Depends(get_admin),
):
    owned = await db.select("chat_logs", {"select": "id", "id": f"eq.{question_id}", "user_id": f"eq.{user.id}"})
    if not owned:
        # Same answer whether it doesn't exist or belongs to someone else.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found.")
    await admin.delete("chat_logs", {"id": f"eq.{question_id}", "user_id": f"eq.{user.id}"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
