"""The real FastAPI app verifying real Supabase tokens."""

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.main import app

from .conftest import _env, integration

pytestmark = [pytest.mark.anyio, *integration]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def api():
    live = Settings(_env_file=None, supabase_url=_env["SUPABASE_URL"], supabase_anon_key=_env["SUPABASE_ANON_KEY"])
    app.dependency_overrides[get_settings] = lambda: live
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            yield client
    app.dependency_overrides.clear()


async def test_backend_identifies_each_user_from_their_token(api, user_a, user_b):
    for user in (user_a, user_b):
        response = await api.get("/me", headers={"Authorization": f"Bearer {user['token']}"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == user["id"]
        assert body["email"] == user["email"]
        assert body["display_name"] == user["full_name"]


async def test_backend_rejects_unauthenticated_and_tampered_requests(api, user_a):
    assert (await api.get("/me")).status_code == 401

    header, payload, signature = user_a["token"].split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}AAAA"
    assert (await api.get("/me", headers={"Authorization": f"Bearer {tampered}"})).status_code == 401

    anon_key_as_token = {"Authorization": f"Bearer {_env['SUPABASE_ANON_KEY']}"}
    assert (await api.get("/me", headers=anon_key_as_token)).status_code == 401
