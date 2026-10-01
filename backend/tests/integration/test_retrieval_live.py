"""pgvector retrieval and lecture-content isolation on the real database, with real embeddings."""

import pytest

from app.core.config import Settings
from app.intelligence.embeddings import FastEmbedEmbedder, to_pgvector

from .conftest import integration

pytestmark = integration

PASSAGES = [
    "To train the model we use gradient descent: take the derivative of the cost and step against it, scaled by the learning rate.",
    "If the hypothesis has too many features it fits the training set but generalizes badly; that is overfitting.",
    "Naive Bayes assumes the features are conditionally independent given the class label.",
    "A support vector machine finds the separating hyperplane with the largest margin between classes.",
]


@pytest.fixture(scope="module")
def embedder():
    return FastEmbedEmbedder(Settings(_env_file=None))


@pytest.fixture(scope="module")
def indexed(supa, user_factory, embedder):
    owner, other = user_factory("vec-owner"), user_factory("vec-other")
    lecture = supa.http.post(
        f"{supa.url}/rest/v1/lectures",
        headers={**supa.service_headers(), "Prefer": "return=representation"},
        json={"user_id": owner["id"], "title": "Retrieval test", "source_type": "audio"},
    ).json()[0]
    vectors = embedder.embed_passages(PASSAGES)
    rows = [
        {"lecture_id": lecture["id"], "sequence": i, "text": text, "start_seconds": i * 60, "end_seconds": i * 60 + 55,
         "first_segment": i, "last_segment": i, "token_estimate": 30, "embedding": to_pgvector(v), "embedding_model": embedder.name}
        for i, (text, v) in enumerate(zip(PASSAGES, vectors))
    ]
    response = supa.http.post(f"{supa.url}/rest/v1/lecture_chunks", headers=supa.service_headers(), json=rows)
    assert response.status_code == 201, response.text
    supa.http.post(
        f"{supa.url}/rest/v1/transcript_segments", headers=supa.service_headers(),
        json=[{"lecture_id": lecture["id"], "sequence": 0, "start_seconds": 0, "end_seconds": 5, "raw_text": "hello", "text": "Hello"}],
    )
    return {"owner": owner, "other": other, "lecture": lecture}


def match(supa, token, lecture_id, vector, count=2):
    return supa.rest(
        "POST", "rpc/match_lecture_chunks", token,
        json={"p_lecture_id": lecture_id, "p_query_embedding": to_pgvector(vector), "p_match_count": count},
    )


@pytest.mark.parametrize(
    "query,expected",
    [
        ("How are the parameters updated during training?", 0),
        ("Why does a complex model fail on new data?", 1),
        ("What independence assumption does the classifier make?", 2),
        ("What is the maximum margin classifier?", 3),
    ],
)
def test_pgvector_returns_the_relevant_chunk_with_timestamps(supa, indexed, embedder, query, expected):
    response = match(supa, indexed["owner"]["token"], indexed["lecture"]["id"], embedder.embed_query(query))
    assert response.status_code == 200, response.text
    top = response.json()[0]
    assert top["sequence"] == expected
    assert float(top["start_seconds"]) == expected * 60 and float(top["end_seconds"]) == expected * 60 + 55
    assert 0 < top["similarity"] <= 1


def test_another_user_cannot_retrieve_or_read_the_lecture_content(supa, indexed, embedder):
    lecture_id = indexed["lecture"]["id"]
    other = indexed["other"]["token"]
    assert match(supa, other, lecture_id, embedder.embed_query("gradient descent")).json() == []
    for table in ("lecture_chunks", "transcript_segments", "transcripts", "chapters", "lecture_intelligence"):
        assert supa.rest("GET", table, other, params={"lecture_id": f"eq.{lecture_id}"}).json() == [], table
    assert len(supa.rest("GET", "lecture_chunks", indexed["owner"]["token"], params={"lecture_id": f"eq.{lecture_id}"}).json()) == 4


def test_clients_cannot_write_lecture_content(supa, indexed):
    owner = indexed["owner"]["token"]
    row = {"lecture_id": indexed["lecture"]["id"], "sequence": 9, "text": "planted", "start_seconds": 0, "end_seconds": 1,
           "first_segment": 0, "last_segment": 0, "token_estimate": 1}
    assert supa.rest("POST", "lecture_chunks", owner, json=row).status_code in (401, 403)
    assert supa.rest("POST", "lecture_intelligence", owner, json={"lecture_id": indexed["lecture"]["id"], "summary": "x", "provider": "x", "model": "x", "prompt_version": "x"}).status_code in (401, 403)
    assert supa.rest("GET", "lecture_chunks", None).status_code in (401, 403)
