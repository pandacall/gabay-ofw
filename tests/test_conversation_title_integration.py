"""LLM-generated Conversation titles at the HTTP seam (spec
2026-09-05-llm-conversation-titles).

Same injection pattern as ``tests/test_chat_api.py`` — a fake token
verifier, ADK's ``InMemorySessionService``, a fake model at the
``BaseLlm`` boundary — plus a fake ``title_model`` (the plain
out-of-band ``ModelCall`` ``ChatService`` invokes directly, never
through the ADK Runner). Nothing internal is mocked.

Starlette's ``TestClient`` runs a response's ``BackgroundTasks``
synchronously as part of handling the request, so by the time
``client.post("/api/chat", ...)`` returns here, the one-time title
attempt has already run (or been skipped) — no polling needed.
"""

from __future__ import annotations

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

DISPATCHER_REPLY = "I hear you. Tell me more about what happened."

ENGLISH_EXTRACTION = json.dumps(
    {
        "language": "en",
        "claims": {"country": {"value": "Qatar", "confidence": "high"}},
        "safety_flags": [],
    }
)


class FakeModelRunner(BaseLlm):
    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    replies: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        if llm_request.config and llm_request.config.response_schema is not None:
            result = self.extraction_results.pop(0)
            if isinstance(result, Exception):
                raise result
            text = result
        else:
            result = self.replies.pop(0) if self.replies else DISPATCHER_REPLY
            if isinstance(result, Exception):
                raise result
            if isinstance(result, types.Content):
                yield LlmResponse(content=result)
                return
            text = result
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


def transfer_to_emergency() -> types.Content:
    return types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="transfer_to_agent", args={"agent_name": "EMERGENCY"}
                )
            )
        ],
    )


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


def auth(uid: str) -> dict:
    return {"Authorization": f"Bearer valid-{uid}"}


def turn(client, text, *, uid="maria", session_id=None):
    body = {"text": text}
    if session_id:
        body["session_id"] = session_id
    response = client.post("/api/chat", json=body, headers=auth(uid))
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line]


def _row(client, session_id, uid="maria"):
    response = client.get("/api/conversations", headers=auth(uid))
    for row in response.json()["conversations"]:
        if row["session_id"] == session_id:
            return row
    raise AssertionError(f"{session_id} not listed")


def _reply_session_id(lines: list[dict]) -> str:
    for line in lines:
        if line["type"] == "reply":
            return line["session_id"]
    raise AssertionError("no reply line")


@pytest.fixture()
def fake_model():
    return FakeModelRunner()


def _client(fake_model, *, title_model):
    service = ChatService(
        session_service=InMemorySessionService(),
        llm=fake_model,
        title_model=title_model,
    )
    app = create_app(verifier=FakeVerifier(), chat_service=service)
    return TestClient(app)


class TestTitleGenerationFiresOnTheFirstTurnOnly:
    def test_a_safe_generated_title_is_written_with_source_llm(self, fake_model):
        calls = []

        async def title_model(prompt: str) -> str:
            calls.append(prompt)
            return "Unpaid wages, several months"

        client = _client(fake_model, title_model=title_model)
        fake_model.extraction_results.append(ENGLISH_EXTRACTION)
        lines = turn(client, "I have not been paid")
        session_id = _reply_session_id(lines)

        assert len(calls) == 1
        row = _row(client, session_id)
        assert row["label"] == "Unpaid wages, several months"
        assert row["label_source"] == "llm"

    def test_never_fires_again_on_a_later_turn(self, fake_model):
        calls = []

        async def title_model(prompt: str) -> str:
            calls.append(prompt)
            return "Unpaid wages"

        client = _client(fake_model, title_model=title_model)
        fake_model.extraction_results.append(ENGLISH_EXTRACTION)
        lines = turn(client, "I have not been paid")
        session_id = _reply_session_id(lines)
        assert len(calls) == 1

        fake_model.extraction_results.append(ENGLISH_EXTRACTION)
        turn(client, "one more thing", session_id=session_id)
        assert len(calls) == 1, "title_model must not be called again on turn 2"

    def test_a_blocked_title_falls_back_to_the_claims_based_label(self, fake_model):
        async def title_model(prompt: str) -> str:
            return "Employer assaulted me"

        client = _client(fake_model, title_model=title_model)
        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "en",
                    "claims": {"months_unpaid": {"value": "5", "confidence": "high"}},
                    "safety_flags": [],
                }
            )
        )
        lines = turn(client, "I have not been paid for 5 months")
        session_id = _reply_session_id(lines)

        row = _row(client, session_id)
        assert row["label"] == "wages"
        assert row["label_source"] == "derived"

    def test_no_title_model_configured_leaves_the_claims_based_system_untouched(
        self, fake_model
    ):
        client = _client(fake_model, title_model=None)
        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "en",
                    "claims": {"months_unpaid": {"value": "5", "confidence": "high"}},
                    "safety_flags": [],
                }
            )
        )
        lines = turn(client, "I have not been paid for 5 months")
        session_id = _reply_session_id(lines)
        row = _row(client, session_id)
        assert row["label"] == "wages"
        assert row["label_source"] == "derived"

    def test_a_claims_derived_label_already_set_is_not_overwritten_by_the_llm_title(
        self, fake_model
    ):
        async def title_model(prompt: str) -> str:
            return "Contract dispute"

        client = _client(fake_model, title_model=title_model)
        # A claim fires on turn one itself, synchronously, before the
        # background title task even runs — the claims-based label wins
        # the write-once race.
        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "en",
                    "claims": {"months_unpaid": {"value": "5", "confidence": "high"}},
                    "safety_flags": [],
                }
            )
        )
        lines = turn(client, "I have not been paid for 5 months")
        session_id = _reply_session_id(lines)
        row = _row(client, session_id)
        assert row["label"] == "wages"
        assert row["label_source"] == "derived"


class TestEmergencyConversationIsNotExcluded:
    """spec 2026-09-05-llm-conversation-titles: a deliberate, accepted
    departure from ``label_state_delta``'s old ``EMERGENCY_CONVERSATION``
    exclusion -- the riskiest Conversations get the same safety-filtered
    LLM attempt as any other, not a hard-coded neutral label forever."""

    def test_a_safe_title_is_generated_inside_the_emergency_conversation(
        self, fake_model
    ):
        async def title_model(prompt: str) -> str:
            return "General inquiry"

        client = _client(fake_model, title_model=title_model)
        button = client.post("/api/emergency/button", headers=auth("maria"))
        assert button.status_code == 200
        emergency_lines = [
            json.loads(line) for line in button.text.splitlines() if line
        ]
        session_id = next(
            line for line in emergency_lines if line["type"] == "case"
        )["session_id"]

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.replies.append(transfer_to_emergency())
        fake_model.replies.append("Nandito ako, kausapin mo ako.")
        turn(client, "tulungan niyo ako", session_id=session_id)

        row = _row(client, session_id)
        assert row["label"] == "General inquiry"
        assert row["label_source"] == "llm"


class TestReplyTextFromLine:
    """The small seam app.main's background-task trigger uses to read
    her turn's reply text out of one raw NDJSON line, without
    re-deriving app.chat's own line-shape knowledge."""

    def test_extracts_text_from_a_reply_line(self):
        from app.chat import reply_text_from_line

        line = json.dumps({"type": "reply", "text": "hello", "session_id": "s"}) + "\n"
        assert reply_text_from_line(line) == "hello"

    def test_ignores_any_other_line_type(self):
        from app.chat import reply_text_from_line

        line = json.dumps({"type": "trail", "text": "hello"}) + "\n"
        assert reply_text_from_line(line) is None

    def test_ignores_malformed_json(self):
        from app.chat import reply_text_from_line

        assert reply_text_from_line("not json\n") is None
