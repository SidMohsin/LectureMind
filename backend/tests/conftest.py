import time
import uuid

import httpx
import jwt
import pytest

from app.core.config import Settings, get_settings
from app.main import app

SUPABASE_URL = "https://project-ref.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
HS_SECRET = "test-legacy-jwt-secret-that-is-long-enough-for-hs256"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def settings():
    test_settings = Settings(
        _env_file=None,
        supabase_url=SUPABASE_URL,
        supabase_anon_key="test-anon-key",
        supabase_jwt_secret=HS_SECRET,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield test_settings
    app.dependency_overrides.clear()


@pytest.fixture
async def client(settings):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


def make_token(
    *,
    sub: str | None = None,
    key=HS_SECRET,
    algorithm: str = "HS256",
    audience: str = "authenticated",
    issuer: str = ISSUER,
    role: str = "authenticated",
    email: str = "student@example.com",
    expires_in: int = 3600,
    issued_offset: int = 0,
    headers: dict | None = None,
) -> str:
    now = int(time.time()) + issued_offset
    claims = {
        "sub": sub or str(uuid.uuid4()),
        "aud": audience,
        "iss": issuer,
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, key, algorithm=algorithm, headers=headers)
