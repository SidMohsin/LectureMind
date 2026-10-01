"""Semantic content search, cross-lecture question history and question deletion (offline)."""

import uuid

import pytest

from app.api import workspace as workspace_api
from app.api.deps import get_user_db
from app.api.search import select_results
from app.main import app

from .conftest import make_token

pytestmark = pytest.mark.anyio

USER_ID = str(uuid.uuid4())
LECTURE_A = str(uuid.uuid4())
LECTURE_B = str(uuid.uuid4())
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def row(lecture_id, sequence, similarity, title="Lecture"):
    return {
        "chunk_id": str(uuid.uuid4()),
        "lecture_id": lecture_id,
        "lecture_title": title,
        "lecture_subject": "ML",
        "lecture_topic": None,
        "lecture_instructor": "Andrew Ng",
        "lecture_date": None,
        "sequence": sequence,
        "text": f"Passage {sequence} about gradient descent.",
        "start_seconds": sequence * 60.0,
        "end_seconds": sequence * 60.0 + 55,
        "similarity": similarity,
    }


def test_results_are_ranked_thresholded_and_capped_per_lecture():
    rows = [row(LECTURE_A, i, 0.9 - i * 0.01) for i in range(5)] + [row(LECTURE_B, 9, 0.7), row(LECTURE_B, 10, 0.5)]
    results = select_results(rows, min_similarity=0.6, per_lecture=3, limit=12)
    assert [r["lecture"]["id"] for r in results] == [LECTURE_A] * 3 + [LECTURE_B]  # cap of 3 for A, B still shown
    assert [r["sequence"] for r in results] == [0, 1, 2, 9]  # best first; 0.5 is below the threshold
    assert results[0]["start_seconds"] == 0.0 and results[3]["start_seconds"] == 540.0  # the chunk's own timestamps
    assert results[0]["lecture"]["title"] == "Lecture" and results[0]["text"].startswith("Passage 0")
    assert select_results(rows, min_similarity=0.6, per_lecture=3, limit=2) == results[:2]
    assert select_results([row(LECTURE_A, 0, 0.3)], min_similarity=0.6, per_lecture=3, limit=12) == []


class FakeEmbedder:
    name = EMBEDDING_MODEL
    dimension = 384

    def __init__(self):
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        return [0.02] * 384


class FakeDb:
    def __init__(self):
        self.calls = []
        self.rpc_rows = [row(LECTURE_A, 3, 0.8, title="Linear Regression")]
        self.chat_logs = []
        self.owned_questions = set()
        self.owned_lectures = {LECTURE_A}

    async def rpc(self, function, args):
        self.calls.append(("rpc", function, args))
        return self.rpc_rows

    async def select(self, table, params):
        self.calls.append(("select", table, params))
        if table == "chat_logs":
            return [{"id": params["id"][3:]}] if params["id"][3:] in self.owned_questions else []
        if table == "lectures":
            lecture_id = params["id"][3:]
            return [{"id": lecture_id, "user_id": USER_ID, "title": "L", "status": "READY"}] if lecture_id in self.owned_lectures else []
        return []

    async def select_counted(self, table, params):
        self.calls.append(("select_counted", table, params))
        return self.chat_logs, len(self.chat_logs)


class FakeAdmin:
    def __init__(self):
        self.deleted = []

    async def delete(self, table, filters):
        self.deleted.append((table, filters))


@pytest.fixture
def db():
    fake = FakeDb()
    app.dependency_overrides[get_user_db] = lambda: fake
    return fake


@pytest.fixture
def embedder(settings):
    fake = FakeEmbedder()
    app.dependency_overrides[workspace_api.get_embedder] = lambda: fake
    return fake


@pytest.fixture
def admin(settings):
    fake = FakeAdmin()
    app.dependency_overrides[workspace_api.get_admin] = lambda: fake
    return fake


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {make_token(sub=USER_ID)}"}


# --- content search --------------------------------------------------------------------------


async def test_content_search_requires_authentication(client, db, embedder):
    assert (await client.get("/search/content", params={"q": "gradient descent"})).status_code == 401


async def test_content_search_embeds_with_the_index_model_and_searches_as_the_user(client, db, embedder, auth, settings):
    response = await client.get("/search/content", params={"q": "  how is   the step size chosen "}, headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "how is the step size chosen" and embedder.queries == ["how is the step size chosen"]
    assert body["embedding_model"] == EMBEDDING_MODEL and body["min_similarity"] == settings.search_min_similarity
    _, function, args = next(call for call in db.calls if call[0] == "rpc")
    assert function == "search_lecture_content"  # user-scoped RPC: only the caller's READY lectures
    assert args["p_embedding_model"] == EMBEDDING_MODEL and args["p_match_count"] == settings.search_candidates
    assert args["p_query_embedding"].startswith("[") and "p_user_id" not in args  # identity comes from the token only
    result = body["results"][0]
    assert result["lecture"] == {"id": LECTURE_A, "title": "Linear Regression", "subject": "ML", "topic": None,
                                 "instructor": "Andrew Ng", "lecture_date": None}
    assert result["start_seconds"] == 180.0 and result["end_seconds"] == 235.0 and body["latency_ms"] >= 0


@pytest.mark.parametrize("query", ["", "ab", "  a  ", "x" * 301])
async def test_content_search_validates_the_query(client, db, embedder, auth, query):
    response = await client.get("/search/content", params={"q": query}, headers=auth)
    assert response.status_code == 422
    assert embedder.queries == [] and not any(call[0] == "rpc" for call in db.calls)


async def test_content_search_with_no_close_match_is_empty(client, db, embedder, auth):
    db.rpc_rows = [row(LECTURE_A, 0, 0.41)]
    body = (await client.get("/search/content", params={"q": "sourdough bread"}, headers=auth)).json()
    assert body["results"] == []


# --- history -----------------------------------------------------------------------------------


async def test_history_is_scoped_filtered_ordered_and_paged(client, db, auth):
    db.chat_logs = [{"id": str(uuid.uuid4()), "lecture": {"id": LECTURE_A, "title": "L"}, "question": "Q?", "outcome": "answered",
                     "answer": "A.", "sources": [], "latency_ms": 5, "created_at": "2026-10-01T10:00:00+00:00"}]
    response = await client.get(
        "/questions", params={"q": 'grad, "descent" (x)', "lecture_id": LECTURE_A, "order": "oldest", "limit": 5, "offset": 10}, headers=auth
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1 and body["items"][0]["lecture"]["id"] == LECTURE_A and body["limit"] == 5 and body["offset"] == 10
    _, table, params = db.calls[-1]
    assert table == "chat_logs" and params["user_id"] == f"eq.{USER_ID}" and params["lecture_id"] == f"eq.{LECTURE_A}"
    assert params["order"] == "created_at.asc,id.asc" and params["limit"] == "5" and params["offset"] == "10"
    # The text filter is quoted, so commas/parentheses/quotes in it can't change the filter structure.
    assert params["or"] == '(question.ilike."*grad, \\"descent\\" (x)*",answer.ilike."*grad, \\"descent\\" (x)*")'
    assert "lecture:lectures(" in params["select"]


async def test_history_rejects_malformed_ids_and_parameters(client, db, auth):
    assert (await client.get("/questions", params={"lecture_id": "not-a-uuid"}, headers=auth)).status_code == 422
    assert (await client.get("/questions", params={"order": "random"}, headers=auth)).status_code == 422
    assert (await client.get("/questions", params={"limit": 1000}, headers=auth)).status_code == 422
    assert (await client.get("/questions")).status_code == 401


async def test_deleting_someone_elses_question_is_not_found_and_deletes_nothing(client, db, admin, auth):
    response = await client.delete(f"/questions/{uuid.uuid4()}", headers=auth)
    assert response.status_code == 404 and admin.deleted == []


async def test_deleting_an_owned_question_is_filtered_by_owner(client, db, admin, auth):
    question = str(uuid.uuid4())
    db.owned_questions.add(question)
    assert (await client.delete(f"/questions/{question}", headers=auth)).status_code == 204
    assert admin.deleted == [("chat_logs", {"id": f"eq.{question}", "user_id": f"eq.{USER_ID}"})]


async def test_clearing_a_lecture_history_requires_owning_the_lecture(client, db, admin, auth):
    assert (await client.delete(f"/lectures/{LECTURE_B}/questions", headers=auth)).status_code == 404
    assert admin.deleted == []
    assert (await client.delete(f"/lectures/{LECTURE_A}/questions", headers=auth)).status_code == 204
    assert admin.deleted == [("chat_logs", {"lecture_id": f"eq.{LECTURE_A}", "user_id": f"eq.{USER_ID}"})]
