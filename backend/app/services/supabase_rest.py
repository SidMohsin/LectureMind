"""User-scoped access to Supabase (PostgREST database API and Storage API).

Requests are sent with the calling user's own access token, so Row Level
Security and storage policies apply to every backend call. Repositories should
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
        self._rest_url = settings.supabase_rest_url
        self._storage_url = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self._headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
        }

    async def _send(self, method: str, url: str, *, label: str, **kwargs) -> httpx.Response:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        try:
            response = await self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("Supabase %s %s failed: %s", method, label, exc)
            raise UpstreamServiceError() from exc

        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired.")
        if response.status_code >= 400:
            logger.error("Supabase %s %s failed with %s: %s", method, label, response.status_code, response.text)
            raise UpstreamServiceError()
        return response

    # --- database ------------------------------------------------------------------------

    async def select(self, table: str, params: dict[str, str]) -> list[dict]:
        response = await self._send("GET", f"{self._rest_url}/{table}", label=table, params=params)
        return response.json()

    async def select_counted(self, table: str, params: dict[str, str]) -> tuple[list[dict], int]:
        response = await self._send(
            "GET", f"{self._rest_url}/{table}", label=table, params=params, headers={"Prefer": "count=exact"}
        )
        # Content-Range: "0-24/57", or "*/0" when nothing matched.
        total = int(response.headers.get("content-range", "*/0").rsplit("/", 1)[1])
        return response.json(), total

    async def delete(self, table: str, params: dict[str, str]) -> list[dict]:
        response = await self._send(
            "DELETE", f"{self._rest_url}/{table}", label=table, params=params, headers={"Prefer": "return=representation"}
        )
        return response.json()

    # --- storage -------------------------------------------------------------------------

    async def list_objects(self, bucket: str, prefix: str) -> list[dict]:
        response = await self._send(
            "POST",
            f"{self._storage_url}/object/list/{bucket}",
            label=f"storage list {bucket}",
            json={"prefix": prefix, "limit": 1000, "offset": 0},
        )
        return response.json()

    async def remove_objects(self, bucket: str, paths: list[str]) -> None:
        await self._send(
            "DELETE", f"{self._storage_url}/object/{bucket}", label=f"storage delete {bucket}", json={"prefixes": paths}
        )
