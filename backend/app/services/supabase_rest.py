"""User-scoped access to Supabase PostgreSQL through its REST (PostgREST) API.

Requests are sent with the calling user's own access token, so the database's
Row Level Security policies apply to every backend query. Repositories should
still filter by the authenticated user's id explicitly (defence in depth).
"""

import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings
from app.core.errors import UpstreamServiceError

logger = logging.getLogger(__name__)


class UserScopedSupabase:
    def __init__(self, http: httpx.AsyncClient, settings: Settings, access_token: str):
        self._http = http
        self._base_url = settings.supabase_rest_url
        self._headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
        }

    async def select(self, table: str, params: dict[str, str]) -> list[dict]:
        try:
            response = await self._http.get(f"{self._base_url}/{table}", params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            logger.error("Supabase request to %s failed: %s", table, exc)
            raise UpstreamServiceError() from exc

        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired.")
        if response.status_code >= 400:
            logger.error("Supabase %s query failed with %s: %s", table, response.status_code, response.text)
            raise UpstreamServiceError()
        return response.json()
