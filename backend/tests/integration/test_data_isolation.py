"""Row Level Security and column privileges, tested with two real users."""

import pytest

from .conftest import integration

pytestmark = integration

RETURN = {"Prefer": "return=representation"}
DENIED = (401, 403)


@pytest.fixture(scope="module")
def lecture_a(supa, user_a):
    response = supa.rest(
        "POST", "lectures", user_a["token"], headers=RETURN, json={"title": "Alice's lecture", "source_type": "audio"}
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


# --- profiles --------------------------------------------------------------------------


def test_profile_created_for_new_user(supa, user_a):
    rows = supa.rest("GET", "profiles", user_a["token"], params={"id": f"eq.{user_a['id']}"}).json()
    assert len(rows) == 1
    assert rows[0]["display_name"] == user_a["full_name"]


def test_user_sees_only_their_own_profile(supa, user_a, user_b):
    assert supa.rest("GET", "profiles", user_a["token"], params={"id": f"eq.{user_b['id']}"}).json() == []
    visible = supa.rest("GET", "profiles", user_a["token"], params={"select": "id"}).json()
    assert visible == [{"id": user_a["id"]}]


def test_profiles_cannot_be_written_by_clients(supa, user_a, user_b):
    assert supa.rest("POST", "profiles", user_a["token"], json={"id": user_b["id"]}).status_code in DENIED
    assert (
        supa.rest(
            "PATCH", "profiles", user_a["token"], params={"id": f"eq.{user_b['id']}"}, json={"display_name": "x"}
        ).status_code
        in DENIED
    )
    assert supa.rest("DELETE", "profiles", user_a["token"], params={"id": f"eq.{user_b['id']}"}).status_code in DENIED


def test_anonymous_requests_cannot_read_profiles_or_lectures(supa):
    assert supa.rest("GET", "profiles", None).status_code in DENIED
    assert supa.rest("GET", "lectures", None).status_code in DENIED


# --- lectures: ownership ---------------------------------------------------------------


def test_new_lecture_is_owned_by_the_caller(lecture_a, user_a):
    assert lecture_a["user_id"] == user_a["id"]
    assert lecture_a["status"] == "UPLOADED"


def test_client_cannot_assign_ownership_to_someone_else(supa, user_a, user_b):
    response = supa.rest(
        "POST",
        "lectures",
        user_a["token"],
        json={"title": "Planted", "source_type": "audio", "user_id": user_b["id"]},
    )
    assert response.status_code in DENIED
    assert supa.rest("GET", "lectures", user_b["token"], params={"title": "eq.Planted"}).json() == []


def test_client_cannot_set_system_managed_status(supa, user_a, lecture_a):
    insert = supa.rest("POST", "lectures", user_a["token"], json={"title": "t", "source_type": "audio", "status": "READY"})
    assert insert.status_code in DENIED
    update = supa.rest("PATCH", "lectures", user_a["token"], params={"id": f"eq.{lecture_a['id']}"}, json={"status": "READY"})
    assert update.status_code in DENIED


def test_owner_can_edit_metadata(supa, user_a, lecture_a):
    response = supa.rest(
        "PATCH",
        "lectures",
        user_a["token"],
        headers=RETURN,
        params={"id": f"eq.{lecture_a['id']}"},
        json={"subject": "Computer Science"},
    )
    assert response.status_code == 200
    assert response.json()[0]["subject"] == "Computer Science"


# --- lectures: cross-user access (IDOR) --------------------------------------------------


def test_other_user_cannot_read_lecture_by_id(supa, user_b, lecture_a):
    assert supa.rest("GET", "lectures", user_b["token"], params={"id": f"eq.{lecture_a['id']}"}).json() == []


def test_other_user_cannot_modify_lecture(supa, user_a, user_b, lecture_a):
    response = supa.rest(
        "PATCH",
        "lectures",
        user_b["token"],
        headers=RETURN,
        params={"id": f"eq.{lecture_a['id']}"},
        json={"title": "Hijacked"},
    )
    assert response.json() == []
    owner_view = supa.rest("GET", "lectures", user_a["token"], params={"id": f"eq.{lecture_a['id']}"}).json()
    assert owner_view[0]["title"] == "Alice's lecture"


def test_other_user_cannot_delete_lecture(supa, user_a, user_b, lecture_a):
    response = supa.rest("DELETE", "lectures", user_b["token"], headers=RETURN, params={"id": f"eq.{lecture_a['id']}"})
    assert response.json() == []
    assert len(supa.rest("GET", "lectures", user_a["token"], params={"id": f"eq.{lecture_a['id']}"}).json()) == 1


def test_owner_cannot_transfer_lecture(supa, user_a, user_b, lecture_a):
    response = supa.rest(
        "PATCH", "lectures", user_a["token"], params={"id": f"eq.{lecture_a['id']}"}, json={"user_id": user_b["id"]}
    )
    assert response.status_code in DENIED


def test_owner_can_delete_own_lecture(supa, user_a):
    created = supa.rest(
        "POST", "lectures", user_a["token"], headers=RETURN, json={"title": "Temporary", "source_type": "video"}
    ).json()[0]
    deleted = supa.rest("DELETE", "lectures", user_a["token"], headers=RETURN, params={"id": f"eq.{created['id']}"})
    assert len(deleted.json()) == 1
