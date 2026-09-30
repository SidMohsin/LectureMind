"""Service-role access to Supabase for trusted server-side code.

This bypasses Row Level Security, so callers must already have established
ownership from the verified access token (API) or from the job record
(worker). User ids written here always come from the token or the job, never
from request input.
"""

import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.core.errors import UpstreamServiceError

logger = logging.getLogger(__name__)


class StorageObjectTooLarge(Exception):
    """Storage rejected the object as larger than the project's file size limit."""


class ConflictError(Exception):
    """A unique constraint rejected the write."""


class ServiceSupabase:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self._http = http
        self._rest = settings.supabase_rest_url
        self._storage = settings.supabase_storage_url
        key = settings.supabase_service_role_key
        self._headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    async def _send(self, method: str, url: str, *, label: str, expect: tuple[int, ...] = (), **kwargs) -> httpx.Response:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        try:
            response = await self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("Supabase %s %s failed: %s", method, label, exc)
            raise UpstreamServiceError() from exc
        if response.status_code in expect:
            return response
        if response.status_code == 409:
            raise ConflictError(response.text)
        if response.status_code >= 400:
            if _is_too_large(response):
                raise StorageObjectTooLarge()
            logger.error("Supabase %s %s failed with %s: %s", method, label, response.status_code, response.text[:500])
            raise UpstreamServiceError()
        return response

    # --- database ------------------------------------------------------------------------

    async def select(self, table: str, params: dict[str, str]) -> list[dict]:
        return (await self._send("GET", f"{self._rest}/{table}", label=table, params=params)).json()

    async def insert(self, table: str, row: dict, *, on_conflict: str | None = None) -> dict:
        prefer = "return=representation"
        params = {}
        if on_conflict:
            prefer += ",resolution=merge-duplicates"
            params["on_conflict"] = on_conflict
        response = await self._send(
            "POST", f"{self._rest}/{table}", label=table, params=params, json=row, headers={"Prefer": prefer}
        )
        return response.json()[0]

    async def update(self, table: str, filters: dict[str, str], values: dict) -> list[dict]:
        """Conditional update; returns the updated rows (empty when the filter matched nothing)."""
        response = await self._send(
            "PATCH", f"{self._rest}/{table}", label=table, params=filters, json=values, headers={"Prefer": "return=representation"}
        )
        return response.json()

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        await self._send("DELETE", f"{self._rest}/{table}", label=table, params=filters)

    async def rpc(self, function: str, args: dict):
        return (await self._send("POST", f"{self._rest}/rpc/{function}", label=f"rpc {function}", json=args)).json()

    # --- storage -------------------------------------------------------------------------

    def _object_url(self, bucket: str, path: str) -> str:
        return f"{self._storage}/object/{bucket}/{quote(path)}"

    async def upload_file(self, bucket: str, path: str, source: Path, content_type: str, *, upsert: bool) -> None:
        async def chunks():
            with source.open("rb") as handle:
                while block := handle.read(1024 * 1024):
                    yield block

        await self._send(
            "POST",
            self._object_url(bucket, path),
            label=f"storage upload {bucket}",
            content=chunks(),
            headers={
                "Content-Type": content_type,
                "Content-Length": str(source.stat().st_size),
                "x-upsert": "true" if upsert else "false",
                "cache-control": "private, max-age=0",
            },
            timeout=httpx.Timeout(30.0, write=None, read=300.0),
        )

    async def download_file(self, bucket: str, path: str, destination: Path, max_bytes: int) -> int:
        """Stream an object to `destination`; refuses objects larger than `max_bytes`."""
        written = 0
        try:
            async with self._http.stream(
                "GET", self._object_url(bucket, path), headers=self._headers, timeout=httpx.Timeout(30.0, read=300.0)
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread())[:300]
                    logger.error("Storage download %s failed with %s: %s", path, response.status_code, body)
                    raise UpstreamServiceError()
                with destination.open("wb") as handle:
                    async for block in response.aiter_bytes(1024 * 1024):
                        written += len(block)
                        if written > max_bytes:
                            raise StorageObjectTooLarge()
                        handle.write(block)
        except httpx.HTTPError as exc:
            logger.error("Storage download %s failed: %s", path, exc)
            raise UpstreamServiceError() from exc
        return written

    async def object_exists(self, bucket: str, path: str) -> bool:
        response = await self._send(
            "GET", f"{self._storage}/object/info/{bucket}/{quote(path)}", label="storage info", expect=(400, 404)
        )
        return response.status_code == 200

    async def remove_objects(self, bucket: str, paths: list[str]) -> None:
        await self._send("DELETE", f"{self._storage}/object/{bucket}", label="storage delete", json={"prefixes": paths})


def _is_too_large(response: httpx.Response) -> bool:
    if response.status_code == 413:
        return True
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and str(body.get("statusCode")) == "413"
