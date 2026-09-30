"""Fixtures for tests that run against a real Supabase project.

Requires backend/.env.test (see .env.test.example). The service-role key in
that file is used ONLY here, to create/confirm/delete throwaway test users.
The application itself never reads it.
"""

import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[2] / ".env.test"
REQUIRED = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "APP_URL")

_env = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
_missing = [name for name in REQUIRED if not _env.get(name)]


integration = [
    pytest.mark.integration,
    pytest.mark.skipif(bool(_missing), reason=f"backend/.env.test missing: {', '.join(_missing)}"),
]


PASSWORD = "Correct-Horse-9-Battery"


class Supabase:
    def __init__(self, env: dict):
        self.url = env["SUPABASE_URL"].rstrip("/")
        self.anon = env["SUPABASE_ANON_KEY"]
        self.service = env["SUPABASE_SERVICE_ROLE_KEY"]
        self.app_url = env["APP_URL"].rstrip("/")
        self.http = httpx.Client(timeout=20.0)

    # --- headers ---
    def anon_headers(self) -> dict:
        return {"apikey": self.anon}

    def user_headers(self, token: str) -> dict:
        return {"apikey": self.anon, "Authorization": f"Bearer {token}"}

    def service_headers(self) -> dict:
        return {"apikey": self.service, "Authorization": f"Bearer {self.service}"}

    # --- auth ---
    def admin_create_user(self, email: str, full_name: str, confirmed: bool = True) -> dict:
        response = self.http.post(
            f"{self.url}/auth/v1/admin/users",
            headers=self.service_headers(),
            json={
                "email": email,
                "password": PASSWORD,
                "email_confirm": confirmed,
                "user_metadata": {"full_name": full_name},
            },
        )
        response.raise_for_status()
        return response.json()

    def admin_generate_link(self, link_type: str, email: str, redirect_to: str, **extra) -> dict:
        response = self.http.post(
            f"{self.url}/auth/v1/admin/generate_link",
            headers=self.service_headers(),
            json={"type": link_type, "email": email, "redirect_to": redirect_to, **extra},
        )
        response.raise_for_status()
        return response.json()

    def admin_delete_user(self, user_id: str) -> None:
        self.http.delete(f"{self.url}/auth/v1/admin/users/{user_id}", headers=self.service_headers())

    def password_login(self, email: str, password: str = PASSWORD) -> httpx.Response:
        return self.http.post(
            f"{self.url}/auth/v1/token",
            params={"grant_type": "password"},
            headers=self.anon_headers(),
            json={"email": email, "password": password},
        )

    def session_for(self, email: str) -> dict:
        response = self.password_login(email)
        response.raise_for_status()
        return response.json()

    # --- data ---
    def rest(self, method: str, path: str, token: str | None, **kwargs) -> httpx.Response:
        headers = self.user_headers(token) if token else self.anon_headers()
        headers.update(kwargs.pop("headers", {}))
        return self.http.request(method, f"{self.url}/rest/v1/{path}", headers=headers, **kwargs)

    def storage(self, method: str, path: str, token: str | None, **kwargs) -> httpx.Response:
        headers = self.user_headers(token) if token else self.anon_headers()
        headers.update(kwargs.pop("headers", {}))
        return self.http.request(method, f"{self.url}/storage/v1/{path}", headers=headers, **kwargs)


@pytest.fixture(scope="session")
def supa():
    client = Supabase(_env)
    yield client
    client.http.close()


@pytest.fixture(scope="session")
def created_users(supa):
    """Tracks every user created during the run so they are always deleted."""
    ids: list[str] = []
    yield ids
    for user_id in ids:
        supa.admin_delete_user(user_id)


def unique_email(label: str) -> str:
    return f"lecturemind-test-{label}-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture(scope="session")
def user_factory(supa, created_users):
    def make(label: str, *, confirmed: bool = True) -> dict:
        email = unique_email(label)
        user = supa.admin_create_user(email, full_name=f"Test {label.title()}", confirmed=confirmed)
        created_users.append(user["id"])
        session = supa.session_for(email) if confirmed else None
        return {
            "id": user["id"],
            "email": email,
            "full_name": f"Test {label.title()}",
            "token": session["access_token"] if session else None,
        }

    return make


@pytest.fixture(scope="session")
def user_a(user_factory):
    return user_factory("alice")


@pytest.fixture(scope="session")
def user_b(user_factory):
    return user_factory("bob")
