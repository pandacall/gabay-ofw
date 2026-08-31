"""Behavioral tests at the HTTP seam (PRD testing decision: primary seam).

A fake token verifier and an in-memory notes store are injected via FastAPI
dependency overrides — no internals of the app are mocked.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import get_current_uid
from app.main import create_app
from app.notes import NotesStore, get_notes_store


class InMemoryNotesStore(NotesStore):
    def __init__(self):
        self._notes: dict[str, list[dict]] = {}

    def put_note(self, uid: str, text: str) -> str:
        notes = self._notes.setdefault(uid, [])
        note_id = f"note-{len(notes) + 1}"
        notes.append({"id": note_id, "text": text})
        return note_id

    def get_notes(self, uid: str) -> list[dict]:
        return list(self._notes.get(uid, []))


class FakeVerifier:
    """Accepts tokens of the form 'valid-<uid>'; rejects everything else."""

    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


@pytest.fixture()
def store():
    return InMemoryNotesStore()


@pytest.fixture()
def client(store):
    app = create_app(verifier=FakeVerifier())
    app.dependency_overrides[get_notes_store] = lambda: store
    return TestClient(app)


def auth(uid: str) -> dict:
    return {"Authorization": f"Bearer valid-{uid}"}


class TestHealth:
    def test_healthz_is_public(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestAuthRejection:
    def test_missing_token_rejected(self, client):
        assert client.get("/api/notes").status_code == 401
        assert client.post("/api/notes", json={"text": "x"}).status_code == 401

    def test_malformed_authorization_header_rejected(self, client):
        r = client.get("/api/notes", headers={"Authorization": "NotBearer abc"})
        assert r.status_code == 401

    def test_invalid_token_rejected(self, client):
        r = client.get("/api/notes", headers={"Authorization": "Bearer bogus"})
        assert r.status_code == 401


class TestNotesRoundTrip:
    def test_write_then_read_own_note(self, client):
        r = client.post("/api/notes", json={"text": "kumusta"}, headers=auth("alice"))
        assert r.status_code == 201
        note_id = r.json()["id"]

        r = client.get("/api/notes", headers=auth("alice"))
        assert r.status_code == 200
        assert r.json()["notes"] == [{"id": note_id, "text": "kumusta"}]

    def test_users_are_isolated(self, client):
        client.post("/api/notes", json={"text": "alice secret"}, headers=auth("alice"))
        r = client.get("/api/notes", headers=auth("bob"))
        assert r.json()["notes"] == []

    def test_empty_text_rejected(self, client):
        r = client.post("/api/notes", json={"text": ""}, headers=auth("alice"))
        assert r.status_code == 422

    def test_missing_text_rejected(self, client):
        r = client.post("/api/notes", json={}, headers=auth("alice"))
        assert r.status_code == 422
