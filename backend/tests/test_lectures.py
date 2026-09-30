import uuid

import pytest

from app.api.deps import get_user_db
from app.core.errors import UpstreamServiceError
from app.main import app
from app.repositories.lectures import search_pattern

from .conftest import make_token

pytestmark = pytest.mark.anyio

USER_ID = str(uuid.uuid4())
LECTURE_ID = str(uuid.uuid4())

LECTURE_ROW = {
    "id": LECTURE_ID,
    "title": "Convex Optimization & Duality",
    "subject": "Computer Science",
    "topic": None,
    "instructor": "Prof. Ng",
    "lecture_date": "2026-09-14",
    "tags": ["optimization"],
    "source_type": "video",
    "source_url": None,
    "status": "READY",
    "duration_seconds": 3522,
    "created_at": "2026-09-29T10:00:00+00:00",
    "updated_at": "2026-09-29T10:00:00+00:00",
}


class FakeDb:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.total = 0
        self.objects = {}
        self.deleted_rows = [LECTURE_ROW]
        self.fail_storage = False

    async def select(self, table, params):
        self.calls.append(("select", table, params))
        return self.rows

    async def select_counted(self, table, params):
        self.calls.append(("select_counted", table, params))
        return self.rows, self.total

    async def delete(self, table, params):
        self.calls.append(("delete", table, params))
        return self.deleted_rows

    async def list_objects(self, bucket, prefix):
        self.calls.append(("list_objects", bucket, prefix))
        return self.objects.get(prefix, [])

    async def remove_objects(self, bucket, paths):
        self.calls.append(("remove_objects", bucket, sorted(paths)))
        if self.fail_storage:
            raise UpstreamServiceError()


@pytest.fixture
def db():
    fake = FakeDb()
    app.dependency_overrides[get_user_db] = lambda: fake
    return fake


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {make_token(sub=USER_ID)}"}


# --- listing ---------------------------------------------------------------------------


async def test_list_requires_authentication(client, db):
    assert (await client.get("/lectures")).status_code == 401
    assert db.calls == []


async def test_list_is_always_scoped_to_the_caller(client, db, auth):
    db.rows, db.total = [LECTURE_ROW], 57

    response = await client.get("/lectures", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 57 and body["limit"] == 25 and body["offset"] == 0
    assert body["items"][0]["title"] == "Convex Optimization & Duality"
    _, table, params = db.calls[0]
    assert table == "lectures"
    assert params["user_id"] == f"eq.{USER_ID}"
    assert params["order"] == "created_at.desc,id.desc"


async def test_client_supplied_user_id_is_ignored(client, db, auth):
    other = str(uuid.uuid4())
    await client.get(f"/lectures?user_id={other}", headers=auth)
    assert db.calls[0][2]["user_id"] == f"eq.{USER_ID}"


async def test_list_filters_and_sort_are_translated(client, db, auth):
    await client.get(
        "/lectures",
        params={
            "q": "Duality",
            "subject": "Computer Science",
            "status": "processing",
            "source_type": "url",
            "sort": "duration",
            "limit": 10,
            "offset": 20,
        },
        headers=auth,
    )
    params = db.calls[0][2]
    assert params["search_text"] == "ilike.*duality*"
    assert params["subject"] == "eq.Computer Science"
    assert params["status"] == "not.in.(READY,FAILED)"
    assert params["source_type"] == "eq.url"
    assert params["order"].startswith("duration_seconds.desc.nullslast")
    assert (params["limit"], params["offset"]) == ("10", "20")


@pytest.mark.parametrize(
    "query",
    [{"status": "archived"}, {"source_type": "pdf"}, {"sort": "random"}, {"limit": 0}, {"limit": 101}, {"offset": -1}],
)
async def test_list_rejects_invalid_parameters(client, db, auth, query):
    response = await client.get("/lectures", params=query, headers=auth)
    assert response.status_code == 422
    assert db.calls == []


def test_search_text_cannot_inject_wildcards():
    assert search_pattern("  Big_O 100% ") == "*big\\_o 100\\%*"
    assert search_pattern("a*b\\c") == "*ab\\\\c*"


async def test_subjects_are_deduplicated_and_scoped(client, db, auth):
    db.rows = [{"subject": "Physics"}, {"subject": "biology"}, {"subject": "Physics"}, {"subject": "  "}]
    response = await client.get("/lectures/subjects", headers=auth)
    assert response.json() == {"subjects": ["biology", "Physics"]}
    assert db.calls[0][2]["user_id"] == f"eq.{USER_ID}"


# --- single lecture --------------------------------------------------------------------


async def test_get_lecture_returns_owned_lecture(client, db, auth):
    db.rows = [LECTURE_ROW]
    response = await client.get(f"/lectures/{LECTURE_ID}", headers=auth)
    assert response.status_code == 200
    params = db.calls[0][2]
    assert params["id"] == f"eq.{LECTURE_ID}" and params["user_id"] == f"eq.{USER_ID}"


async def test_get_lecture_not_owned_is_404(client, db, auth):
    response = await client.get(f"/lectures/{uuid.uuid4()}", headers=auth)
    assert response.status_code == 404
    assert response.json()["message"] == "Lecture not found."


async def test_get_lecture_rejects_malformed_id(client, db, auth):
    assert (await client.get("/lectures/not-a-uuid", headers=auth)).status_code == 422
    assert db.calls == []


# --- deletion --------------------------------------------------------------------------


async def test_delete_not_owned_is_404_and_touches_nothing(client, db, auth):
    response = await client.delete(f"/lectures/{LECTURE_ID}", headers=auth)
    assert response.status_code == 404
    assert [call[0] for call in db.calls] == ["select"]


async def test_delete_removes_media_before_the_lecture(client, db, auth):
    db.rows = [LECTURE_ROW]
    base = f"{USER_ID}/{LECTURE_ID}/"
    db.objects = {
        base: [{"name": "original", "id": None}, {"name": "processed", "id": None}],
        f"{base}original/": [{"name": "lecture.mp4", "id": "o1"}],
        f"{base}processed/": [{"name": "audio.wav", "id": "o2"}],
    }

    response = await client.delete(f"/lectures/{LECTURE_ID}", headers=auth)

    assert response.status_code == 204
    kinds = [call[0] for call in db.calls]
    assert kinds.index("remove_objects") < kinds.index("delete")
    removed = next(call for call in db.calls if call[0] == "remove_objects")
    assert removed[2] == [f"{base}original/lecture.mp4", f"{base}processed/audio.wav"]
    deleted = next(call for call in db.calls if call[0] == "delete")
    assert deleted[2] == {"id": f"eq.{LECTURE_ID}", "user_id": f"eq.{USER_ID}"}


async def test_delete_keeps_lecture_when_media_cleanup_fails(client, db, auth):
    db.rows = [LECTURE_ROW]
    db.objects = {f"{USER_ID}/{LECTURE_ID}/": [{"name": "x.mp3", "id": "o1"}]}
    db.fail_storage = True

    response = await client.delete(f"/lectures/{LECTURE_ID}", headers=auth)

    assert response.status_code == 502
    assert "delete" not in [call[0] for call in db.calls]
