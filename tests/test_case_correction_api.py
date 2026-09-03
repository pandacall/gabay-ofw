"""One-tap correction behavioral tests at the HTTP seam (issue #44, PRD #34).

Same pattern as tests/test_chat_api.py: a fake token verifier and the ADK
in-memory session service injected through the app factory, no internals
mocked. ``POST /api/case/correct`` is the authenticated endpoint a UI tap
calls directly — never a conversation turn, never an agent tool (same
house style as mark_safe/panic_wipe: a nonce-gated backend endpoint would
overreach here since a correction is neither destructive nor irreversible,
but it is still bearer-token authenticated and session-scoped exactly like
every other per-user write in this app).
"""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field

from app.agent import GEMINI_MODEL
from app.chat import ChatService
from app.main import create_app

TAGLISH_EXTRACTION = json.dumps(
    {
        "language": "taglish",
        "claims": {
            "country": {"value": "Kuwait", "confidence": "high"},
            "months_unpaid": {"value": "3", "confidence": "high"},
        },
        "safety_flags": [],
    }
)


class FakeModelRunner(BaseLlm):
    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    replies: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        if llm_request.config and llm_request.config.response_schema is not None:
            self.calls.append("extraction")
            result = self.extraction_results.pop(0)
            if isinstance(result, Exception):
                raise result
            text = result
        else:
            self.calls.append("dispatcher")
            text = self.replies.pop(0) if self.replies else "OK"
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


@pytest.fixture()
def fake_model():
    return FakeModelRunner()


@pytest.fixture()
def client(fake_model):
    service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
    app = create_app(verifier=FakeVerifier(), chat_service=service)
    return TestClient(app)


def auth(uid: str) -> dict:
    return {"Authorization": f"Bearer valid-{uid}"}


def turn(client, text, *, uid="maria", session_id=None):
    body = {"text": text}
    if session_id is not None:
        body["session_id"] = session_id
    response = client.post("/api/chat", json=body, headers=auth(uid))
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    return {line["type"]: line for line in lines}


def correct(client, *, session_id, field, value, uid="maria"):
    return client.post(
        "/api/case/correct",
        json={"session_id": session_id, "field": field, "value": value},
        headers=auth(uid),
    )


class TestAuthAndSessionScoping:
    def test_requires_token(self, client):
        response = client.post(
            "/api/case/correct",
            json={"session_id": "whatever", "field": "country", "value": "Qatar"},
        )
        assert response.status_code == 401

    def test_unknown_session_is_404(self, client):
        response = correct(client, session_id="nope", field="country", value="Qatar")
        assert response.status_code == 404

    def test_another_users_session_is_404(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type = turn(client, "Nasa Kuwait ako")
        session_id = by_type["reply"]["session_id"]

        response = correct(
            client,
            session_id=session_id,
            field="country",
            value="Qatar",
            uid="intruder",
        )
        assert response.status_code == 404

    def test_unknown_field_is_rejected(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type = turn(client, "Nasa Kuwait ako")
        session_id = by_type["reply"]["session_id"]

        response = correct(
            client, session_id=session_id, field="not_a_field", value="x"
        )
        assert response.status_code == 422


class TestOneTapCorrection:
    def test_correction_sets_user_confirmed_and_updates_the_case(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type = turn(client, "Nasa Kuwait ako, hindi ako nababayaran")
        session_id = by_type["reply"]["session_id"]
        assert by_type["case"]["case"]["claims"]["country"]["value"] == "Kuwait"

        response = correct(
            client, session_id=session_id, field="country", value="Saudi Arabia"
        )
        assert response.status_code == 200
        claim = response.json()["case"]["claims"]["country"]
        assert claim["value"] == "Saudi Arabia"
        assert claim["user_confirmed"] is True
        assert claim["source"] == "user"

    def test_correction_survives_a_later_disagreeing_extraction(
        self, client, fake_model
    ):
        # Demoable fixture (PRD #34): she corrects her country in one tap;
        # a later turn's extraction disagreeing must never revert it —
        # only raise a Conflict.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type = turn(client, "Nasa Kuwait ako")
        session_id = by_type["reply"]["session_id"]

        correct(client, session_id=session_id, field="country", value="Saudi Arabia")

        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "taglish",
                    "claims": {"country": {"value": "Qatar", "confidence": "high"}},
                    "safety_flags": [],
                }
            )
        )
        by_type = turn(client, "sa Qatar na pala ako", session_id=session_id)
        claim = by_type["case"]["case"]["claims"]["country"]
        assert claim["value"] == "Saudi Arabia"
        assert claim["user_confirmed"] is True
        assert claim["conflicts"][-1]["value"] == "Qatar"

    def test_correction_unblocks_a_previously_conflicted_field(
        self, client, fake_model
    ):
        # She confirms her country in one tap; a later turn's extraction
        # disagrees, raising a Conflict on a SequencerIn field that would
        # block FILING_SEQUENCER. Her one-tap correction resolves it and
        # unblocks sequencing again.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type = turn(client, "Nasa Kuwait ako")
        session_id = by_type["reply"]["session_id"]

        correct(client, session_id=session_id, field="country", value="Kuwait")

        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "taglish",
                    "claims": {"country": {"value": "Qatar", "confidence": "high"}},
                    "safety_flags": [],
                }
            )
        )
        by_type = turn(client, "sa Qatar na pala ako", session_id=session_id)
        case_with_conflict = by_type["case"]["case"]
        assert case_with_conflict["claims"]["country"]["conflicts"]

        from app.case import unresolved_sequencer_conflict

        assert unresolved_sequencer_conflict(case_with_conflict) == "country"

        response = correct(
            client, session_id=session_id, field="country", value="Kuwait"
        )
        updated_case = response.json()["case"]
        assert unresolved_sequencer_conflict(updated_case) is None
