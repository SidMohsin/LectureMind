"""The lecture library API against the real project, with two real users.

Lecture rows are created by each test user through their own RLS-scoped
access (ingestion arrives in a later phase) and removed with the users.
"""

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.main import app

from .conftest import _env, integration

pytestmark = [pytest.mark.anyio, *integration]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def create(supa, user, **fields) -> dict:
    body = {"source_type": "audio", **fields}
    if body["source_type"] == "url":
        body.setdefault("source_url", "https://www.youtube.com/watch?v=abc")
    response = supa.rest("POST", "lectures", user["token"], headers={"Prefer": "return=representation"}, json=body)
    assert response.status_code == 201, response.text
    return response.json()[0]


@pytest.fixture(scope="module")
def library(supa, user_factory):
    carol = user_factory("carol")
    dave = user_factory("dave")
    lectures = {
        "optimization": create(
            supa, carol, title="Convex Optimization", subject="Computer Science", tags=["duality", "kkt"], source_type="video"
        ),
        "macro": create(supa, carol, title="Macroeconomic Policy", subject="Economics", instructor="Dr. Reinhart", source_type="url"),
        "quantum": create(supa, carol, title="Wave-Particle Duality", subject="Physics", topic="Quantum mechanics"),
        "dave": create(supa, dave, title="Dave's Private Lecture", subject="Physics"),
    }
    return {"carol": carol, "dave": dave, "lectures": lectures}


@pytest.fixture
async def api():
    live = Settings(_env_file=None, supabase_url=_env["SUPABASE_URL"], supabase_anon_key=_env["SUPABASE_ANON_KEY"])
    app.dependency_overrides[get_settings] = lambda: live
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            yield client
    app.dependency_overrides.clear()


def as_user(user):
    return {"Authorization": f"Bearer {user['token']}"}


async def titles(api, user, **params):
    response = await api.get("/lectures", params=params, headers=as_user(user))
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


async def test_each_user_lists_only_their_own_lectures(api, library):
    carol_titles = await titles(api, library["carol"])
    assert sorted(carol_titles) == ["Convex Optimization", "Macroeconomic Policy", "Wave-Particle Duality"]
    assert await titles(api, library["dave"]) == ["Dave's Private Lecture"]


async def test_search_matches_title_subject_instructor_and_tags(api, library):
    carol = library["carol"]
    assert sorted(await titles(api, carol, q="duality")) == ["Convex Optimization", "Wave-Particle Duality"]
    assert await titles(api, carol, q="reinhart") == ["Macroeconomic Policy"]
    assert await titles(api, carol, q="QUANTUM") == ["Wave-Particle Duality"]
    assert await titles(api, carol, q="100%") == []
    assert await titles(api, carol, q="Private") == []  # Dave's lecture is invisible to Carol


async def test_filters_sort_and_pagination(api, library):
    carol = library["carol"]
    assert await titles(api, carol, source_type="url") == ["Macroeconomic Policy"]
    assert await titles(api, carol, subject="Physics") == ["Wave-Particle Duality"]
    assert await titles(api, carol, status="ready") == []
    assert len(await titles(api, carol, status="processing")) == 3  # new lectures start as UPLOADED
    assert await titles(api, carol, sort="title") == sorted(await titles(api, carol), key=str.casefold)

    page = (await api.get("/lectures", params={"limit": 2, "offset": 2}, headers=as_user(carol))).json()
    assert page["total"] == 3 and len(page["items"]) == 1


async def test_subjects_are_per_user(api, library):
    carol = (await api.get("/lectures/subjects", headers=as_user(library["carol"]))).json()
    assert carol == {"subjects": ["Computer Science", "Economics", "Physics"]}
    dave = (await api.get("/lectures/subjects", headers=as_user(library["dave"]))).json()
    assert dave == {"subjects": ["Physics"]}


async def test_opening_another_users_lecture_by_id_is_404(api, library):
    daves = library["lectures"]["dave"]["id"]
    assert (await api.get(f"/lectures/{daves}", headers=as_user(library["carol"]))).status_code == 404
    assert (await api.get(f"/lectures/{daves}", headers=as_user(library["dave"]))).status_code == 200


async def test_deleting_another_users_lecture_is_404_and_keeps_it(api, library):
    daves = library["lectures"]["dave"]["id"]
    assert (await api.delete(f"/lectures/{daves}", headers=as_user(library["carol"]))).status_code == 404
    assert (await api.get(f"/lectures/{daves}", headers=as_user(library["dave"]))).status_code == 200


async def test_delete_removes_lecture_and_its_media(api, supa, library):
    carol = library["carol"]
    lecture = create(supa, carol, title="Temporary Lecture", subject="Scratch")
    path = f"{carol['id']}/{lecture['id']}/original/recording.mp3"
    upload = supa.storage(
        "POST", f"object/lectures/{path}", carol["token"], content=b"ID3" + b"\0" * 32, headers={"Content-Type": "audio/mpeg"}
    )
    assert upload.status_code == 200, upload.text

    response = await api.delete(f"/lectures/{lecture['id']}", headers=as_user(carol))

    assert response.status_code == 204
    assert (await api.get(f"/lectures/{lecture['id']}", headers=as_user(carol))).status_code == 404
    leftover = supa.http.post(
        f"{supa.url}/storage/v1/object/list/lectures",
        headers=supa.service_headers(),
        json={"prefix": f"{carol['id']}/{lecture['id']}/original/"},
    ).json()
    assert leftover == []


async def test_lecture_api_requires_a_valid_session(api, library):
    assert (await api.get("/lectures")).status_code == 401
    assert (await api.get("/lectures", headers={"Authorization": "Bearer nonsense"})).status_code == 401
