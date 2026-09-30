import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_current_user, get_user_db
from app.core.security import AuthenticatedUser
from app.repositories import lectures as repo
from app.schemas.lectures import Lecture, LectureList, SubjectList
from app.services.supabase_rest import UserScopedSupabase

router = APIRouter(prefix="/lectures", tags=["lectures"])

NOT_FOUND = "Lecture not found."


@router.get("", response_model=LectureList)
async def list_lectures(
    q: str | None = Query(default=None, max_length=100),
    subject: str | None = Query(default=None, max_length=120),
    status_group: repo.StatusGroup | None = Query(default=None, alias="status"),
    source_type: repo.SourceType | None = None,
    sort: repo.SortOrder = "newest",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    items, total = await repo.list_lectures(
        db,
        user.id,
        query=q,
        subject=subject,
        status_group=status_group,
        source_type=source_type,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return LectureList(items=items, total=total, limit=limit, offset=offset)


@router.get("/subjects", response_model=SubjectList)
async def list_subjects(
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    return SubjectList(subjects=await repo.list_subjects(db, user.id))


@router.get("/{lecture_id}", response_model=Lecture)
async def get_lecture(
    lecture_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    lecture = await repo.get_lecture(db, user.id, lecture_id)
    if lecture is None:
        # Same answer whether the lecture doesn't exist or belongs to someone else.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return lecture


@router.delete("/{lecture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lecture(
    lecture_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    if not await repo.delete_lecture(db, user.id, lecture_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
