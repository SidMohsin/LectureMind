"""Private lecture media storage, tested with two real users."""

import uuid

import pytest

from .conftest import integration

pytestmark = integration

BUCKET = "lectures"
AUDIO = b"ID3" + b"\x00" * 64


@pytest.fixture(scope="module")
def uploaded_paths(supa):
    paths: list[str] = []
    yield paths
    if paths:
        supa.http.request(
            "DELETE",
            f"{supa.url}/storage/v1/object/{BUCKET}",
            headers=supa.service_headers(),
            json={"prefixes": paths},
        )


def create_lecture(supa, user) -> str:
    response = supa.rest(
        "POST",
        "lectures",
        user["token"],
        headers={"Prefer": "return=representation"},
        json={"title": "Media test", "source_type": "audio"},
    )
    assert response.status_code == 201, response.text
    return response.json()[0]["id"]


def upload(supa, token, path, body=AUDIO, content_type="audio/mpeg"):
    return supa.storage(
        "POST", f"object/{BUCKET}/{path}", token, content=body, headers={"Content-Type": content_type}
    )


@pytest.fixture(scope="module")
def owned_object(supa, user_a, uploaded_paths):
    path = f"{user_a['id']}/{create_lecture(supa, user_a)}/original/sample.mp3"
    response = upload(supa, user_a["token"], path)
    assert response.status_code == 200, response.text
    uploaded_paths.append(path)
    return path


def test_bucket_is_private(supa):
    bucket = supa.http.get(f"{supa.url}/storage/v1/bucket/{BUCKET}", headers=supa.service_headers()).json()
    assert bucket["public"] is False


def test_owner_can_download_their_media(supa, user_a, owned_object):
    response = supa.storage("GET", f"object/authenticated/{BUCKET}/{owned_object}", user_a["token"])
    assert response.status_code == 200
    assert response.content == AUDIO


def test_public_url_does_not_serve_private_media(supa, owned_object):
    response = supa.http.get(f"{supa.url}/storage/v1/object/public/{BUCKET}/{owned_object}")
    assert response.status_code >= 400
    assert response.content != AUDIO


def test_anonymous_request_cannot_download_media(supa, owned_object):
    response = supa.storage("GET", f"object/authenticated/{BUCKET}/{owned_object}", None)
    assert response.status_code >= 400


def test_other_user_cannot_download_media(supa, user_b, owned_object):
    response = supa.storage("GET", f"object/authenticated/{BUCKET}/{owned_object}", user_b["token"])
    assert response.status_code >= 400
    assert response.content != AUDIO


def test_other_user_cannot_list_owner_folder(supa, user_a, user_b, owned_object):
    response = supa.storage(
        "POST", f"object/list/{BUCKET}", user_b["token"], json={"prefix": f"{user_a['id']}/", "limit": 100}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_other_user_cannot_overwrite_or_delete_media(supa, user_b, owned_object, user_a):
    overwrite = supa.storage(
        "PUT", f"object/{BUCKET}/{owned_object}", user_b["token"], content=b"evil", headers={"Content-Type": "audio/mpeg"}
    )
    assert overwrite.status_code >= 400

    supa.storage("DELETE", f"object/{BUCKET}", user_b["token"], json={"prefixes": [owned_object]})
    still_there = supa.storage("GET", f"object/authenticated/{BUCKET}/{owned_object}", user_a["token"])
    assert still_there.content == AUDIO


def test_user_cannot_upload_into_another_users_folder(supa, user_a, user_b, uploaded_paths):
    path = f"{user_b['id']}/{create_lecture(supa, user_b)}/original/planted.mp3"
    response = upload(supa, user_a["token"], path)
    if response.status_code == 200:
        uploaded_paths.append(path)
    assert response.status_code >= 400


def test_upload_requires_an_owned_lecture_folder(supa, user_a, uploaded_paths):
    path = f"{user_a['id']}/{uuid.uuid4()}/original/orphan.mp3"
    response = upload(supa, user_a["token"], path)
    if response.status_code == 200:
        uploaded_paths.append(path)
    assert response.status_code >= 400


def test_bucket_rejects_non_media_types(supa, user_a, uploaded_paths):
    path = f"{user_a['id']}/{create_lecture(supa, user_a)}/original/notes.html"
    response = upload(supa, user_a["token"], path, body=b"<script>alert(1)</script>", content_type="text/html")
    if response.status_code == 200:
        uploaded_paths.append(path)
    assert response.status_code >= 400
