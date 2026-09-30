import uuid
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.api.deps import get_user_db
from app.core import security
from app.core.config import Settings, get_settings
from app.core.errors import UpstreamServiceError
from app.main import app
from app.services.supabase_rest import UserScopedSupabase

from .conftest import SUPABASE_URL, make_token

pytestmark = pytest.mark.anyio

CREATED_AT = "2026-09-29T10:00:00+00:00"


class FakeUserDb:
    """Stands in for UserScopedSupabase and records what was queried."""

    def __init__(self, rows=None, error: Exception | None = None):
        self.rows = rows if rows is not None else []
        self.error = error
        self.calls = []

    async def select(self, table, params):
        self.calls.append((table, params))
        if self.error:
            raise self.error
        return self.rows


@pytest.fixture
def fake_db():
    db = FakeUserDb()
    app.dependency_overrides[get_user_db] = lambda: db
    return db


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- unauthenticated / invalid tokens -------------------------------------------------


async def test_missing_token_is_rejected(client, fake_db):
    response = await client.get("/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["message"] == "Authentication required."
    assert fake_db.calls == []


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        make_token(key="a-different-secret-of-sufficient-length-xx"),
        make_token(expires_in=-60),
        make_token(audience="some-other-audience"),
        make_token(issuer="https://attacker.example/auth/v1"),
        make_token(role="anon"),
        make_token(sub="not-a-uuid"),
    ],
    ids=["malformed", "wrong-secret", "expired", "wrong-audience", "wrong-issuer", "anon-role", "non-uuid-sub"],
)
async def test_invalid_tokens_are_rejected(client, fake_db, token):
    response = await client.get("/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["message"] == "Your session is invalid or has expired."
    assert fake_db.calls == []


async def test_unsigned_alg_none_token_is_rejected(client, fake_db):
    token = jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated"}, key=None, algorithm="none")
    response = await client.get("/me", headers=bearer(token))
    assert response.status_code == 401


async def test_hs256_rejected_when_no_legacy_secret_configured(client, fake_db, settings):
    no_secret = settings.model_copy(update={"supabase_jwt_secret": ""})
    app.dependency_overrides[get_settings] = lambda: no_secret
    response = await client.get("/me", headers=bearer(make_token()))
    assert response.status_code == 401


async def test_auth_not_configured_returns_503(client, fake_db):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    response = await client.get("/me", headers=bearer(make_token()))
    assert response.status_code == 503


# --- authenticated identity -----------------------------------------------------------


async def test_valid_hs256_token_identifies_user(client, fake_db):
    user_id = str(uuid.uuid4())
    fake_db.rows = [{"id": user_id, "display_name": "Alex Chen", "created_at": CREATED_AT}]

    response = await client.get("/me", headers=bearer(make_token(sub=user_id, email="alex@example.com")))

    assert response.status_code == 200
    assert response.json() == {
        "id": user_id,
        "email": "alex@example.com",
        "display_name": "Alex Chen",
        "created_at": "2026-09-29T10:00:00Z",
    }
    # Ownership is derived from the token, never from the request.
    assert fake_db.calls == [("profiles", {"select": "id,display_name,created_at", "id": f"eq.{user_id}"})]


async def test_small_clock_skew_is_tolerated(client, fake_db):
    # Supabase's clock slightly ahead of ours: token issued "2s in the future".
    fake_db.rows = [{"id": "x", "display_name": None, "created_at": CREATED_AT}]
    response = await client.get("/me", headers=bearer(make_token(issued_offset=2)))
    assert response.status_code == 200


async def test_token_issued_far_in_the_future_is_rejected(client, fake_db):
    response = await client.get("/me", headers=bearer(make_token(issued_offset=600)))
    assert response.status_code == 401


async def test_missing_profile_returns_404(client, fake_db):
    response = await client.get("/me", headers=bearer(make_token()))
    assert response.status_code == 404


async def test_upstream_failure_is_not_leaked(client, fake_db):
    fake_db.error = UpstreamServiceError()
    response = await client.get("/me", headers=bearer(make_token()))
    assert response.status_code == 502
    assert response.json()["code"] == "upstream_error"


# --- asymmetric (JWKS) signing keys ---------------------------------------------------


class FakeJwks:
    def __init__(self, public_key=None, error: Exception | None = None):
        self.public_key = public_key
        self.error = error

    def get_signing_key_from_jwt(self, token):
        if self.error:
            raise self.error
        return SimpleNamespace(key=self.public_key)


@pytest.fixture
def ec_key():
    return ec.generate_private_key(ec.SECP256R1())


def use_jwks(monkeypatch, fake):
    monkeypatch.setattr(security, "_jwks_client", lambda url: fake)


async def test_valid_es256_token_verified_via_jwks(client, fake_db, ec_key, monkeypatch):
    use_jwks(monkeypatch, FakeJwks(ec_key.public_key()))
    user_id = str(uuid.uuid4())
    fake_db.rows = [{"id": user_id, "display_name": None, "created_at": CREATED_AT}]

    token = make_token(sub=user_id, key=ec_key, algorithm="ES256", headers={"kid": "k1"})
    response = await client.get("/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["id"] == user_id


async def test_es256_token_signed_by_foreign_key_is_rejected(client, fake_db, ec_key, monkeypatch):
    use_jwks(monkeypatch, FakeJwks(ec.generate_private_key(ec.SECP256R1()).public_key()))
    token = make_token(key=ec_key, algorithm="ES256", headers={"kid": "k1"})
    response = await client.get("/me", headers=bearer(token))
    assert response.status_code == 401


async def test_unknown_signing_key_is_rejected(client, fake_db, ec_key, monkeypatch):
    use_jwks(monkeypatch, FakeJwks(error=jwt.PyJWKClientError("kid not found")))
    token = make_token(key=ec_key, algorithm="ES256", headers={"kid": "unknown"})
    response = await client.get("/me", headers=bearer(token))
    assert response.status_code == 401


async def test_unreachable_jwks_returns_503(client, fake_db, ec_key, monkeypatch):
    use_jwks(monkeypatch, FakeJwks(error=jwt.PyJWKClientConnectionError("timeout")))
    token = make_token(key=ec_key, algorithm="ES256", headers={"kid": "k1"})
    response = await client.get("/me", headers=bearer(token))
    assert response.status_code == 503


# --- user-scoped Supabase client ------------------------------------------------------


async def test_user_scoped_client_forwards_callers_token(settings):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["apikey"] = request.headers["apikey"]
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json=[{"id": "x"}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        db = UserScopedSupabase(http, settings, "user-access-token")
        rows = await db.select("profiles", {"id": "eq.x"})

    assert rows == [{"id": "x"}]
    assert seen["url"] == f"{SUPABASE_URL}/rest/v1/profiles?id=eq.x"
    assert seen["apikey"] == "test-anon-key"
    assert seen["authorization"] == "Bearer user-access-token"


@pytest.mark.parametrize("status_code, expected", [(401, "http_401"), (500, "upstream"), (None, "upstream")])
async def test_user_scoped_client_error_mapping(settings, status_code, expected):
    def handler(request):
        if status_code is None:
            raise httpx.ConnectError("down")
        return httpx.Response(status_code, json={"message": "internal detail"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        db = UserScopedSupabase(http, settings, "token")
        if expected == "upstream":
            with pytest.raises(UpstreamServiceError):
                await db.select("profiles", {})
        else:
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await db.select("profiles", {})
            assert exc_info.value.status_code == 401
