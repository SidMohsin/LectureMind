"""Permission regression matrix against the real project (Phase 7B).

User A owns a lecture with a row in every lecture-owned table and a stored media
object. User B (a valid, logged-in user) and an anonymous caller then try every read
and write path: PostgREST tables, the retrieval/search functions, Storage, and the
API. Nothing of A's may be readable or writable. Run after any migration that touches
RLS, grants or functions.
"""

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.intelligence.embeddings import to_pgvector
from app.main import app

from .conftest import _env, integration

pytestmark = [pytest.mark.anyio, *integration]

VECTOR = to_pgvector([0.05] * 384)
CONTENT_TABLES = (
    "lectures", "lecture_media", "processing_jobs", "transcripts", "transcript_segments",
    "lecture_chunks", "chapters", "lecture_intelligence", "chat_logs",
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def world(supa, user_factory):
    owner, other = user_factory("matrix-owner"), user_factory("matrix-other")
    service = {**supa.service_headers(), "Prefer": "return=representation"}

    def post(table, body):
        response = supa.http.post(f"{supa.url}/rest/v1/{table}", headers=service, json=body)
        assert response.status_code == 201, (table, response.text)
        return response.json()[0]

    lecture = post("lectures", {"user_id": owner["id"], "title": "Matrix lecture", "source_type": "audio", "status": "READY"})
    lid = lecture["id"]
    path = f"{owner['id']}/{lid}/original/source.mp3"
    stored = supa.http.post(
        f"{supa.url}/storage/v1/object/lectures/{path}",
        headers={**supa.service_headers(), "Content-Type": "audio/mpeg"},
        content=b"ID3" + b"\0" * 64,
    )
    assert stored.status_code == 200, stored.text
    post("lecture_media", {"lecture_id": lid, "kind": "original", "storage_path": path, "mime_type": "audio/mpeg", "file_size": 67})
    job = post("processing_jobs", {"lecture_id": lid, "user_id": owner["id"], "status": "succeeded"})
    post("processing_stage_runs", {"job_id": job["id"], "stage": "EXTRACTING_AUDIO", "attempt": 1, "status": "succeeded"})
    post("transcripts", {"lecture_id": lid, "language": "en", "audio_duration_seconds": 5, "segment_count": 1, "model": "m"})
    post("transcript_segments", {"lecture_id": lid, "sequence": 0, "start_seconds": 0, "end_seconds": 5, "raw_text": "secret", "text": "Secret"})
    chunk = post("lecture_chunks", {
        "lecture_id": lid, "sequence": 0, "text": "Secret lecture content.", "start_seconds": 0, "end_seconds": 5,
        "first_segment": 0, "last_segment": 0, "token_estimate": 4, "embedding": VECTOR, "embedding_model": "BAAI/bge-small-en-v1.5",
    })
    post("chapters", {"lecture_id": lid, "sequence": 0, "title": "Secret chapter", "start_seconds": 0, "end_seconds": 5, "first_chunk": 0, "last_chunk": 0})
    post("lecture_intelligence", {"lecture_id": lid, "summary": "Secret summary of the lecture.", "provider": "p", "model": "m", "prompt_version": "v"})
    question = post("chat_logs", {
        "lecture_id": lid, "user_id": owner["id"], "question": "Secret question?", "outcome": "answered",
        "answer": "Secret answer.", "embedding_model": "m", "latency_ms": 1,
    })
    yield {"owner": owner, "other": other, "lecture": lecture, "path": path, "job": job, "chunk": chunk, "question": question}
    supa.http.request("DELETE", f"{supa.url}/storage/v1/object/lectures", headers=supa.service_headers(), json={"prefixes": [path]})


def test_owner_sees_their_rows(supa, world):
    token = world["owner"]["token"]
    for table in CONTENT_TABLES:
        rows = supa.rest("GET", table, token, params={"select": "*", "id" if table == "lectures" else "lecture_id": f"eq.{world['lecture']['id']}"}).json()
        assert rows, table


@pytest.mark.parametrize("who", ["other", "anon"])
def test_no_other_caller_can_read_any_table(supa, world, who):
    token = world["other"]["token"] if who == "other" else None
    lid = world["lecture"]["id"]
    for table in CONTENT_TABLES:
        response = supa.rest("GET", table, token, params={"select": "*", "id" if table == "lectures" else "lecture_id": f"eq.{lid}"})
        assert response.status_code in (200, 401, 403), (table, response.status_code)
        assert response.status_code != 200 or response.json() == [], table
    runs = supa.rest("GET", "processing_stage_runs", token, params={"select": "*", "job_id": f"eq.{world['job']['id']}"})
    assert runs.status_code != 200 or runs.json() == []


def test_other_user_cannot_write_any_table(supa, world):
    token, lid = world["other"]["token"], world["lecture"]["id"]
    for table in CONTENT_TABLES:
        key = "id" if table == "lectures" else "lecture_id"
        patch = supa.rest("PATCH", table, token, params={key: f"eq.{lid}"}, headers={"Prefer": "return=representation"}, json={"updated_at": "2000-01-01T00:00:00Z"} if table in ("lectures", "lecture_media", "processing_jobs") else {"lecture_id": lid})
        assert patch.status_code in (401, 403) or patch.json() == [], (table, patch.status_code, patch.text[:120])
        delete = supa.rest("DELETE", table, token, params={key: f"eq.{lid}"}, headers={"Prefer": "return=representation"})
        assert delete.status_code in (401, 403) or delete.json() == [], (table, delete.status_code)
    forged = supa.rest("POST", "chat_logs", token, json={"lecture_id": lid, "user_id": world["other"]["id"], "question": "x?",
                                                         "outcome": "answered", "answer": "y", "embedding_model": "m", "latency_ms": 1})
    assert forged.status_code in (401, 403)
    # The owner's rows are all still there.
    owner = world["owner"]["token"]
    for table in CONTENT_TABLES:
        key = "id" if table == "lectures" else "lecture_id"
        assert supa.rest("GET", table, owner, params={"select": key, key: f"eq.{lid}"}).json(), table


@pytest.mark.parametrize("who", ["other", "anon"])
def test_retrieval_functions_and_storage_are_scoped(supa, world, who):
    token = world["other"]["token"] if who == "other" else None
    lid = world["lecture"]["id"]
    match = supa.rest("POST", "rpc/match_lecture_chunks", token, json={"p_lecture_id": lid, "p_query_embedding": VECTOR, "p_match_count": 5})
    assert match.status_code in (401, 403) or match.json() == []
    search = supa.rest("POST", "rpc/search_lecture_content", token,
                       json={"p_query_embedding": VECTOR, "p_embedding_model": "BAAI/bge-small-en-v1.5", "p_match_count": 50})
    assert search.status_code in (401, 403) or all(row["lecture_id"] != lid for row in search.json())
    for function in ("claim_processing_job", "recover_processing_jobs", "renew_processing_lease"):
        assert supa.rest("POST", f"rpc/{function}", token, json={}).status_code in (400, 401, 403, 404), function
    sign = supa.storage("POST", f"object/sign/lectures/{world['path']}", token, json={"expiresIn": 60})
    assert sign.status_code >= 400
    assert supa.storage("GET", f"object/authenticated/lectures/{world['path']}", token).status_code >= 400
    assert supa.http.get(f"{supa.url}/storage/v1/object/public/lectures/{world['path']}").status_code >= 400


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


async def test_every_api_route_hides_another_users_lecture(api, world):
    headers = {"Authorization": f"Bearer {world['other']['token']}"}
    lid = world["lecture"]["id"]
    for method, path in [
        ("GET", f"/lectures/{lid}"), ("GET", f"/lectures/{lid}/workspace"), ("GET", f"/lectures/{lid}/media"),
        ("GET", f"/lectures/{lid}/questions"), ("POST", f"/lectures/{lid}/questions"), ("GET", f"/lectures/{lid}/processing"),
        ("POST", f"/lectures/{lid}/retry"), ("DELETE", f"/lectures/{lid}/questions"), ("DELETE", f"/questions/{world['question']['id']}"),
        ("DELETE", f"/lectures/{lid}"),
    ]:
        response = await api.request(method, path, headers=headers, json={"question": "What is secret?"} if method == "POST" else None)
        assert response.status_code == 404, (method, path, response.status_code)
        assert "Secret" not in response.text
    history = (await api.get("/questions", params={"lecture_id": lid}, headers=headers)).json()
    assert history["items"] == [] and history["total"] == 0
    library = (await api.get("/lectures", params={"q": "Matrix"}, headers=headers)).json()
    assert all(item["id"] != lid for item in library["items"])
