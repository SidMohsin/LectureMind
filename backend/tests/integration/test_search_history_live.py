"""Search + question history against the real project with two real users and real embeddings:
content search scope (own READY lectures, same embedding model), history isolation, deleting
questions, and lecture deletion removing that lecture's history only."""

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.intelligence.embeddings import FastEmbedEmbedder, to_pgvector
from app.main import app

from .conftest import _env, integration

pytestmark = [pytest.mark.anyio, *integration]

ALICE_PASSAGES = [
    "Gradient descent repeatedly updates the parameters in the direction of the negative gradient, scaled by the learning rate.",
    "The honor code allows discussing homework with classmates, but each student must write up their own solutions.",
]
BOB_PASSAGES = [
    "Photosynthesis converts light energy into chemical energy stored as glucose in the chloroplasts of plant cells.",
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def embedder():
    return FastEmbedEmbedder(Settings(_env_file=None))


def make_lecture(supa, embedder, owner, title, passages, *, status="READY", model=None):
    headers = {**supa.service_headers(), "Prefer": "return=representation"}
    lecture = supa.http.post(
        f"{supa.url}/rest/v1/lectures", headers=headers,
        json={"user_id": owner["id"], "title": title, "subject": "Testing", "source_type": "audio", "status": status},
    ).json()[0]
    vectors = embedder.embed_passages(passages)
    rows = [
        {"lecture_id": lecture["id"], "sequence": i, "text": t, "start_seconds": i * 90, "end_seconds": i * 90 + 80, "first_segment": i,
         "last_segment": i, "token_estimate": 30, "embedding": to_pgvector(v), "embedding_model": model or embedder.name}
        for i, (t, v) in enumerate(zip(passages, vectors))
    ]
    response = supa.http.post(f"{supa.url}/rest/v1/lecture_chunks", headers=supa.service_headers(), json=rows)
    assert response.status_code == 201, response.text
    return lecture


def add_question(supa, owner, lecture, question):
    response = supa.http.post(
        f"{supa.url}/rest/v1/chat_logs", headers={**supa.service_headers(), "Prefer": "return=representation"},
        json={"lecture_id": lecture["id"], "user_id": owner["id"], "question": question, "outcome": "answered",
              "answer": f"Answer to {question}", "embedding_model": "m", "latency_ms": 5,
              "sources": [{"number": 1, "chunk_id": "x", "sequence": 0, "start_seconds": 0, "end_seconds": 80, "similarity": 0.8, "text": "t", "cited": True}]},
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


@pytest.fixture(scope="module")
def world(supa, user_factory, embedder):
    alice, bob = user_factory("search-alice"), user_factory("search-bob")
    ml = make_lecture(supa, embedder, alice, "Alice ML lecture", ALICE_PASSAGES)
    processing = make_lecture(supa, embedder, alice, "Alice unfinished lecture", ["Gradient descent minimizes the cost function step by step."], status="EMBEDDING")
    other_model = make_lecture(supa, embedder, alice, "Alice old-model lecture", ["Gradient descent with a learning rate."], model="some/other-model")
    biology = make_lecture(supa, embedder, bob, "Bob biology lecture", BOB_PASSAGES)
    questions = {
        "ml": add_question(supa, alice, ml, "What is gradient descent?"),
        "ml2": add_question(supa, alice, ml, "What does the honor code allow?"),
        "bob": add_question(supa, bob, biology, "What is photosynthesis?"),
    }
    return {"alice": alice, "bob": bob, "ml": ml, "processing": processing, "other_model": other_model, "biology": biology, "q": questions}


@pytest.fixture
async def api():
    live = Settings(
        _env_file=None, supabase_url=_env["SUPABASE_URL"], supabase_anon_key=_env["SUPABASE_ANON_KEY"],
        supabase_service_role_key=_env["SUPABASE_SERVICE_ROLE_KEY"],
    )
    app.dependency_overrides[get_settings] = lambda: live
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=60) as client:
            yield client
    app.dependency_overrides.clear()


def as_user(user):
    return {"Authorization": f"Bearer {user['token']}"}


async def search(api, user, q):
    response = await api.get("/search/content", params={"q": q}, headers=as_user(user))
    assert response.status_code == 200, response.text
    return response.json()["results"]


async def test_content_search_finds_the_relevant_passage_with_lecture_and_timestamp(api, world):
    results = await search(api, world["alice"], "how are parameters updated during training")
    assert results, "no results"
    top = results[0]
    assert top["lecture"]["id"] == world["ml"]["id"] and top["lecture"]["title"] == "Alice ML lecture"
    assert top["sequence"] == 0 and top["start_seconds"] == 0 and top["end_seconds"] == 80
    assert top["text"] == ALICE_PASSAGES[0]
    honor = await search(api, world["alice"], "rules for collaborating on homework")
    assert honor[0]["sequence"] == 1 and honor[0]["start_seconds"] == 90


async def test_content_search_only_covers_the_callers_ready_same_model_lectures(api, world):
    lecture_ids = {r["lecture"]["id"] for r in await search(api, world["alice"], "gradient descent learning rate")}
    assert lecture_ids == {world["ml"]["id"]}  # not the unfinished lecture, not the other-model one, not Bob's
    # Bob can't find Alice's content, even with her exact wording.
    assert {r["lecture"]["id"] for r in await search(api, world["bob"], ALICE_PASSAGES[0])} <= {world["biology"]["id"]}
    assert not any(r["lecture"]["id"] == world["biology"]["id"] for r in await search(api, world["alice"], BOB_PASSAGES[0]))


async def test_calling_the_search_function_directly_is_still_scoped(supa, world, embedder):
    vector = to_pgvector(embedder.embed_query(ALICE_PASSAGES[0]))
    args = {"p_query_embedding": vector, "p_embedding_model": embedder.name, "p_match_count": 50}
    rows = supa.rest("POST", "rpc/search_lecture_content", world["bob"]["token"], json=args).json()
    assert {row["lecture_id"] for row in rows} == {world["biology"]["id"]}
    assert supa.rest("POST", "rpc/search_lecture_content", None, json=args).status_code in (401, 403)


async def test_history_lists_only_the_callers_questions_with_their_lecture(api, world):
    response = await api.get("/questions", headers=as_user(world["alice"]))
    assert response.status_code == 200
    body = response.json()
    assert {item["question"] for item in body["items"]} >= {"What is gradient descent?", "What does the honor code allow?"}
    assert all(item["lecture"]["id"] == world["ml"]["id"] for item in body["items"])
    assert "What is photosynthesis?" not in {item["question"] for item in body["items"]}
    created = [item["created_at"] for item in body["items"]]
    assert created == sorted(created, reverse=True)  # newest first

    honor = (await api.get("/questions", params={"q": "honor"}, headers=as_user(world["alice"]))).json()
    assert [item["question"] for item in honor["items"]] == ["What does the honor code allow?"]


async def test_changing_ids_never_exposes_another_users_history(api, world, supa):
    bob = as_user(world["bob"])
    filtered = (await api.get("/questions", params={"lecture_id": world["ml"]["id"]}, headers=bob)).json()
    assert filtered["items"] == [] and filtered["total"] == 0
    assert (await api.delete(f"/questions/{world['q']['ml']['id']}", headers=bob)).status_code == 404
    assert (await api.delete(f"/lectures/{world['ml']['id']}/questions", headers=bob)).status_code == 404
    still = supa.rest("GET", "chat_logs", world["alice"]["token"], params={"select": "id", "id": f"eq.{world['q']['ml']['id']}"}).json()
    assert len(still) == 1


async def test_owner_can_delete_a_question(api, world, supa):
    question = add_question(supa, world["alice"], world["ml"], "Temporary question to delete")
    assert (await api.delete(f"/questions/{question['id']}", headers=as_user(world["alice"]))).status_code == 204
    assert supa.rest("GET", "chat_logs", world["alice"]["token"], params={"select": "id", "id": f"eq.{question['id']}"}).json() == []


async def test_deleting_a_lecture_removes_its_history_and_nothing_else(api, world, supa, embedder):
    alice = world["alice"]
    doomed = make_lecture(supa, embedder, alice, "Alice lecture to delete", ["Backpropagation computes gradients layer by layer."])
    doomed_question = add_question(supa, alice, doomed, "What is backpropagation?")
    assert (await api.delete(f"/lectures/{doomed['id']}", headers=as_user(alice))).status_code == 204

    service = supa.http.get(
        f"{supa.url}/rest/v1/chat_logs", headers=supa.service_headers(), params={"select": "id", "lecture_id": f"eq.{doomed['id']}"}
    ).json()
    assert service == []  # removed with the lecture, not just hidden
    history = (await api.get("/questions", headers=as_user(alice))).json()
    assert doomed_question["id"] not in {item["id"] for item in history["items"]}
    assert world["q"]["ml"]["id"] in {item["id"] for item in history["items"]}  # unrelated history kept
    bob_history = (await api.get("/questions", headers=as_user(world["bob"]))).json()
    assert world["q"]["bob"]["id"] in {item["id"] for item in bob_history["items"]}
