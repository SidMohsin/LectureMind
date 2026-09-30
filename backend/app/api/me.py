from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_user_db
from app.core.security import AuthenticatedUser
from app.repositories.profiles import get_profile
from app.schemas.me import MeResponse
from app.services.supabase_rest import UserScopedSupabase

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    profile = await get_profile(db, user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=profile["display_name"],
        created_at=profile["created_at"],
    )
