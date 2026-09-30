"""Supabase Auth flows exercised against the real project.

Email delivery itself can't be automated here, so verification and recovery
links are generated with the admin API (exactly the links Supabase would
email) and then followed like a browser would.
"""

from urllib.parse import parse_qs, urlparse

from .conftest import PASSWORD, integration, unique_email

pytestmark = integration


def follow_email_link(supa, action_link: str) -> dict:
    """Open a Supabase email link and return what it redirects the browser to."""
    response = supa.http.get(action_link, follow_redirects=False)
    assert response.status_code in (302, 303), response.text
    location = urlparse(response.headers["location"])
    params = {k: v[0] for k, v in parse_qs(location.fragment).items()}
    params.update({k: v[0] for k, v in parse_qs(location.query).items()})
    return {"url": f"{location.scheme}://{location.netloc}{location.path}", "params": params}


def test_unverified_user_cannot_log_in_until_link_is_followed(supa, created_users):
    email = unique_email("verify")
    link = supa.admin_generate_link(
        "signup", email, redirect_to=f"{supa.app_url}/verify", password=PASSWORD, data={"full_name": "Verify Me"}
    )
    created_users.append(link["id"])

    blocked = supa.password_login(email)
    assert blocked.status_code == 400
    assert blocked.json()["error_code"] == "email_not_confirmed"

    redirect = follow_email_link(supa, link["action_link"])
    assert redirect["url"] == f"{supa.app_url}/verify"
    assert redirect["params"].get("type") == "signup"
    assert redirect["params"].get("access_token")

    assert supa.password_login(email).status_code == 200


def test_verification_link_cannot_be_reused(supa, created_users):
    email = unique_email("reuse")
    link = supa.admin_generate_link("signup", email, redirect_to=f"{supa.app_url}/verify", password=PASSWORD)
    created_users.append(link["id"])

    follow_email_link(supa, link["action_link"])
    second = follow_email_link(supa, link["action_link"])

    assert "access_token" not in second["params"]
    assert second["params"].get("error_code") == "otp_expired"


def test_forged_verification_link_is_rejected(supa):
    response = supa.http.get(
        f"{supa.url}/auth/v1/verify",
        params={"token": "0" * 56, "type": "signup", "redirect_to": f"{supa.app_url}/verify"},
        follow_redirects=False,
    )
    location = response.headers.get("location", "")
    assert "access_token" not in location
    assert response.status_code >= 400 or "error" in location


def test_redirect_to_unlisted_origin_is_not_honoured(supa, user_factory):
    user = user_factory("redirect")
    link = supa.admin_generate_link("recovery", user["email"], redirect_to="https://evil.example/steal")
    redirect = follow_email_link(supa, link["action_link"])
    assert not redirect["url"].startswith("https://evil.example")


def test_invalid_credentials_are_rejected(supa, user_a):
    response = supa.password_login(user_a["email"], "definitely-not-the-password")
    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_credentials"


def test_unknown_email_gets_same_error_as_wrong_password(supa):
    response = supa.password_login(unique_email("ghost"), "whatever-password")
    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_credentials"


def test_password_reset_via_recovery_link(supa, user_factory):
    user = user_factory("recovery")
    link = supa.admin_generate_link("recovery", user["email"], redirect_to=f"{supa.app_url}/reset-password")

    redirect = follow_email_link(supa, link["action_link"])
    assert redirect["url"] == f"{supa.app_url}/reset-password"
    assert redirect["params"].get("type") == "recovery"
    recovery_token = redirect["params"]["access_token"]

    new_password = "Brand-New-Password-42"
    updated = supa.http.put(
        f"{supa.url}/auth/v1/user", headers=supa.user_headers(recovery_token), json={"password": new_password}
    )
    assert updated.status_code == 200, updated.text

    assert supa.password_login(user["email"], PASSWORD).status_code == 400
    assert supa.password_login(user["email"], new_password).status_code == 200

    reused = follow_email_link(supa, link["action_link"])
    assert "access_token" not in reused["params"]


def test_logout_revokes_the_refresh_token(supa, user_factory):
    user = user_factory("logout")
    session = supa.session_for(user["email"])

    logout = supa.http.post(f"{supa.url}/auth/v1/logout", headers=supa.user_headers(session["access_token"]))
    assert logout.status_code == 204

    refresh = supa.http.post(
        f"{supa.url}/auth/v1/token",
        params={"grant_type": "refresh_token"},
        headers=supa.anon_headers(),
        json={"refresh_token": session["refresh_token"]},
    )
    assert refresh.status_code in (400, 401)


def test_refresh_token_restores_a_session(supa, user_a):
    session = supa.session_for(user_a["email"])
    refresh = supa.http.post(
        f"{supa.url}/auth/v1/token",
        params={"grant_type": "refresh_token"},
        headers=supa.anon_headers(),
        json={"refresh_token": session["refresh_token"]},
    )
    assert refresh.status_code == 200
    assert refresh.json()["user"]["id"] == user_a["id"]
