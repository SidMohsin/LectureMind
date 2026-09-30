import pytest

pytestmark = pytest.mark.anyio


async def test_health_is_public(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_unknown_route_uses_standard_error_shape(client):
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
    assert set(response.json()) == {"message", "code", "details"}


async def test_cors_allows_configured_origin_only(client):
    preflight = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}

    allowed = await client.options("/me", headers={"Origin": "http://localhost:5173", **preflight})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    denied = await client.options("/me", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in denied.headers


async def test_cors_preflight_allows_the_idempotency_header_on_uploads(client):
    response = await client.options(
        "/lectures/uploads",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,idempotency-key",
        },
    )
    assert response.status_code == 200
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()
