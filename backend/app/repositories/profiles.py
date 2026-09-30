import uuid

from app.services.supabase_rest import UserScopedSupabase


async def get_profile(db: UserScopedSupabase, user_id: uuid.UUID) -> dict | None:
    rows = await db.select(
        "profiles",
        params={"select": "id,display_name,created_at", "id": f"eq.{user_id}"},
    )
    return rows[0] if rows else None
