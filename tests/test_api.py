"""Behavioral tests at the HTTP seam (PRD testing decision: primary seam).

A fake token verifier and an in-memory notes store are injected via FastAPI
dependency overrides — no internals of the app are mocked.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.auth import get_current_uid
from app import main
from app.agent import GEMINI_MODEL
from app.chat import ChatService
from app.deletion import DeletionReason, DeletionResult, get_user_deleter
from app.main import create_app
from app.nonces import InMemoryNonceStore, get_nonce_store
from app.notes import NotesStore, get_notes_store
from app.retention import get_retention_sweeper


class _NeverCalledLlm(BaseLlm):
    """mark_safe never runs the model (app.chat.apply_mark_safe mutates
    the Case directly, outside the Runner) — this fake fails the test
    if it is ever asked to generate."""

    model: str = GEMINI_MODEL

    async def generate_content_async(self, llm_request, stream: bool = False):
        raise AssertionError("mark_safe must never invoke the model")
        yield LlmResponse(content=types.Content(role="model", parts=[]))


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


class FakeDeleter:
    """Records wipe calls at the boundary; no Firestore involved."""

    def __init__(self):
        self.calls: list[tuple[str, DeletionReason]] = []

    def wipe(self, uid: str, *, reason: DeletionReason) -> DeletionResult:
        self.calls.append((uid, reason))
        return DeletionResult(uid=uid, reason=reason, documents_deleted=4)


class FakeSweeper:
    def __init__(self):
        self.calls = []

    def sweep(self, *, now):
        self.calls.append(now)
        return []


@pytest.fixture()
def store():
    return InMemoryNotesStore()


@pytest.fixture()
def deleter():
    return FakeDeleter()


@pytest.fixture()
def sweeper():
    return FakeSweeper()


@pytest.fixture()
def client(store, deleter, sweeper):
    chat_service = ChatService(
        session_service=InMemorySessionService(), llm=_NeverCalledLlm()
    )
    app = create_app(verifier=FakeVerifier(), chat_service=chat_service)
    nonce_store = InMemoryNonceStore()
    app.dependency_overrides[get_notes_store] = lambda: store
    app.dependency_overrides[get_user_deleter] = lambda: deleter
    app.dependency_overrides[get_retention_sweeper] = lambda: sweeper
    app.dependency_overrides[get_nonce_store] = lambda: nonce_store
    return TestClient(app)


def auth(uid: str) -> dict:
    return {"Authorization": f"Bearer valid-{uid}"}


class TestHealth:
    def test_health_is_public(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_production_app_starts_with_cloud_services():
    app = main.production_app()

    assert TestClient(app).get("/api/health").json() == {"status": "ok"}


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


def wipe_nonce(client, uid: str) -> str:
    return client.post("/api/panic-wipe/nonce", headers=auth(uid)).json()["nonce"]


class TestPanicWipe:
    """panic_wipe is a nonce-gated backend endpoint (never an agent tool)."""

    def test_requires_auth(self, client, deleter):
        assert client.post("/api/panic-wipe/nonce").status_code == 401
        assert client.post("/api/panic-wipe", json={"nonce": "x"}).status_code == 401
        assert deleter.calls == []

    def test_rejects_a_nonce_it_never_issued(self, client, deleter):
        r = client.post(
            "/api/panic-wipe", json={"nonce": "forged"}, headers=auth("alice")
        )
        assert r.status_code == 403
        assert deleter.calls == []

    def test_wipes_the_subtree_with_the_panic_wipe_reason(self, client, deleter):
        nonce = wipe_nonce(client, "alice")
        r = client.post(
            "/api/panic-wipe", json={"nonce": nonce}, headers=auth("alice")
        )
        assert r.status_code == 200
        assert r.json()["wiped"] is True
        assert deleter.calls == [("alice", DeletionReason.PANIC_WIPE)]

    def test_nonce_is_single_use(self, client, deleter):
        nonce = wipe_nonce(client, "alice")
        first = client.post(
            "/api/panic-wipe", json={"nonce": nonce}, headers=auth("alice")
        )
        replay = client.post(
            "/api/panic-wipe", json={"nonce": nonce}, headers=auth("alice")
        )
        assert first.status_code == 200
        assert replay.status_code == 403
        assert len(deleter.calls) == 1

    def test_nonce_is_bound_to_the_issuing_user(self, client, deleter):
        nonce = wipe_nonce(client, "alice")
        r = client.post(
            "/api/panic-wipe", json={"nonce": nonce}, headers=auth("bob")
        )
        assert r.status_code == 403
        assert deleter.calls == []

    def test_wipe_nonce_is_not_valid_for_mark_safe(self, client, deleter):
        nonce = wipe_nonce(client, "alice")
        r = client.post(
            "/api/mark-safe", json={"nonce": nonce}, headers=auth("alice")
        )
        assert r.status_code == 403
        # And the wipe nonce still works for its own action.
        r = client.post(
            "/api/panic-wipe", json={"nonce": nonce}, headers=auth("alice")
        )
        assert r.status_code == 200


class TestMarkSafe:
    """mark_safe (issue #41): nonce-gated, clears the Imminent Danger
    PREDICATE only, never the safety flag, and never runs the model."""

    def test_requires_auth(self, client):
        assert client.post("/api/mark-safe/nonce").status_code == 401
        assert client.post("/api/mark-safe", json={"nonce": "x"}).status_code == 401

    def test_rejects_an_unissued_nonce(self, client):
        r = client.post(
            "/api/mark-safe", json={"nonce": "forged"}, headers=auth("alice")
        )
        assert r.status_code == 403

    def test_valid_nonce_clears_the_predicate_with_zero_model_calls(
        self, client, deleter
    ):
        button = client.post("/api/emergency/button", headers=auth("alice"))
        assert button.status_code == 200
        lines = [line for line in button.text.splitlines() if line]
        assert lines  # the card streamed, zero model calls (_NeverCalledLlm)

        nonce = client.post(
            "/api/mark-safe/nonce", headers=auth("alice")
        ).json()["nonce"]
        r = client.post(
            "/api/mark-safe", json={"nonce": nonce}, headers=auth("alice")
        )
        assert r.status_code == 200
        assert r.json()["marked_safe"] is True
        assert r.json()["case"]["emergency"]["active"] is False
        # mark_safe never deletes anything.
        assert deleter.calls == []

    def test_nonce_is_single_use(self, client):
        nonce = client.post(
            "/api/mark-safe/nonce", headers=auth("alice")
        ).json()["nonce"]
        first = client.post(
            "/api/mark-safe", json={"nonce": nonce}, headers=auth("alice")
        )
        replay = client.post(
            "/api/mark-safe", json={"nonce": nonce}, headers=auth("alice")
        )
        assert first.status_code == 200
        assert replay.status_code == 403


class TestRetentionSweep:
    def test_unconfigured_sweep_is_disabled(self, client, sweeper, monkeypatch):
        monkeypatch.delenv("RETENTION_SWEEP_TOKEN", raising=False)
        assert client.post("/api/internal/retention-sweep").status_code == 503
        assert sweeper.calls == []

    def test_rejects_a_wrong_token(self, client, sweeper, monkeypatch):
        monkeypatch.setenv("RETENTION_SWEEP_TOKEN", "sweep-secret")
        r = client.post(
            "/api/internal/retention-sweep",
            headers={"X-Retention-Sweep-Token": "wrong"},
        )
        assert r.status_code == 403
        assert sweeper.calls == []

    def test_runs_the_sweep_with_the_shared_secret(self, client, sweeper, monkeypatch):
        monkeypatch.setenv("RETENTION_SWEEP_TOKEN", "sweep-secret")
        r = client.post(
            "/api/internal/retention-sweep",
            headers={"X-Retention-Sweep-Token": "sweep-secret"},
        )
        assert r.status_code == 200
        assert r.json() == {"expired_users": 0}
        assert len(sweeper.calls) == 1
