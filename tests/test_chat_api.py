"""Conversation-spine behavioral tests at the HTTP seam (PRD #34, primary seam).

A fake token verifier, the ADK in-memory session service, and a fake model
runner are injected through the app factory — no internals are mocked. The
fake model runner sits at the model boundary (ADK's BaseLlm): a request
carrying a response schema is the extraction call; anything else is the
DISPATCHER turn.
"""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field

from app.agent import ACKNOWLEDGEMENTS, GEMINI_MODEL
from app.chat import ChatService
from app.main import create_app

DISPATCHER_REPLY = "Nandito ako para tumulong. Ilang buwan ka nang hindi nababayaran?"

TAGLISH_EXTRACTION = json.dumps(
    {
        "language": "taglish",
        "claims": {
            "country": {"value": "Saudi Arabia", "confidence": "high"},
            "months_unpaid": {"value": "3", "confidence": "high"},
            "employer_name": {"value": "Al Rashid", "confidence": "medium"},
        },
        "safety_flags": ["PASSPORT_WITHHELD"],
    }
)


class FakeModelRunner(BaseLlm):
    """Serves both model touchpoints: typed extraction and DISPATCHER."""

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
            text = self.replies.pop(0) if self.replies else DISPATCHER_REPLY
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
    return {line["type"]: line for line in lines}, lines


class TestAuthRejection:
    def test_chat_requires_token(self, client):
        assert client.post("/api/chat", json={"text": "help"}).status_code == 401

    def test_unknown_session_is_404(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        response = client.post(
            "/api/chat",
            json={"text": "hi", "session_id": "nope"},
            headers=auth("maria"),
        )
        assert response.status_code == 404

    def test_sessions_are_per_user(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type, _ = turn(client, "Hindi ako nababayaran")
        session_id = by_type["reply"]["session_id"]
        response = client.post(
            "/api/chat",
            json={"text": "hi", "session_id": session_id},
            headers=auth("intruder"),
        )
        assert response.status_code == 404


class TestConversationSpine:
    def test_extraction_lands_in_case_and_reply_is_dispatchers(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type, _ = turn(
            client, "Hindi ako nababayaran ng 3 months, kinuha pa ang passport ko"
        )

        # The reply is DISPATCHER's voice, not the extractor's JSON.
        assert by_type["reply"]["text"] == DISPATCHER_REPLY

        case = by_type["case"]["case"]
        assert case["claims"]["months_unpaid"]["value"] == "3"
        assert case["claims"]["country"]["value"] == "Saudi Arabia"
        assert case["claims"]["months_unpaid"]["source"] == "extraction"
        assert "at" in case["claims"]["months_unpaid"]
        assert "PASSPORT_WITHHELD" in case["safety_flags"]
        assert case["language"] == "taglish"

    def test_extraction_runs_before_dispatcher_never_parallel(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        turn(client, "Hindi ako nababayaran")
        assert fake_model.calls == ["extraction", "dispatcher"]

    def test_ack_streams_first_and_turn_one_is_english(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type, lines = turn(client, "Hindi ako nababayaran")
        assert lines[0]["type"] == "ack"
        assert lines[0]["text"] == ACKNOWLEDGEMENTS["en"]

    def test_turn_two_ack_mirrors_recorded_language_as_pure_filipino(
        self, client, fake_model
    ):
        # issue #67: a "taglish"-recorded turn renders the pure Filipino
        # acknowledgement — never a Taglish-worded one.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type, _ = turn(client, "Hindi ako nababayaran")
        session_id = by_type["reply"]["session_id"]

        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        _, lines = turn(client, "Ano ang gagawin ko?", session_id=session_id)
        assert lines[0]["type"] == "ack"
        assert lines[0]["text"] == ACKNOWLEDGEMENTS["tl"]

    def test_ack_streams_even_when_every_model_call_fails(self, client, fake_model):
        # The acknowledgement is fixed app code: it must not depend on any
        # model call succeeding.
        fake_model.extraction_results.append(RuntimeError("model down"))
        fake_model.replies.append(DISPATCHER_REPLY)
        _, lines = turn(client, "help")
        assert lines[0]["type"] == "ack"
        assert lines[0]["text"] == ACKNOWLEDGEMENTS["en"]

    def test_taglish_demo_turn(self, client, fake_model):
        # Demoable: a Taglish message about unpaid wages produces a Taglish
        # reply and a populated Case.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.replies.append(DISPATCHER_REPLY)
        by_type, _ = turn(client, "Hindi ako nababayaran, 3 months na po")
        assert "nababayaran" in by_type["reply"]["text"]
        assert by_type["case"]["case"]["claims"]


class TestExtractionFailsClosed:
    @pytest.mark.parametrize(
        "failure",
        [
            "this is not json at all",
            json.dumps({"language": "klingon", "claims": {}}),
            RuntimeError("429 RESOURCE_EXHAUSTED"),
        ],
        ids=["unparseable-json", "schema-invalid", "transport-error"],
    )
    def test_failure_leaves_case_unchanged_with_warm_reply(
        self, client, fake_model, failure
    ):
        # Seed a real case on turn 1.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type, _ = turn(client, "Hindi ako nababayaran ng 3 months")
        session_id = by_type["reply"]["session_id"]
        case_before = by_type["case"]["case"]

        fake_model.extraction_results.append(failure)
        fake_model.replies.append(DISPATCHER_REPLY)
        by_type, _ = turn(client, "ewan ko na po", session_id=session_id)

        assert by_type["case"]["case"] == case_before
        assert by_type["reply"]["text"] == DISPATCHER_REPLY

    def test_failure_on_first_turn_keeps_case_empty(self, client, fake_model):
        fake_model.extraction_results.append(RuntimeError("safety block"))
        by_type, _ = turn(client, "help me please")
        assert by_type["case"]["case"] == {}
        assert by_type["reply"]["text"] == DISPATCHER_REPLY


class TestCasePersistsAcrossTurns:
    def test_second_turn_merges_onto_first(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type, _ = turn(client, "Hindi ako nababayaran")
        session_id = by_type["reply"]["session_id"]

        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "taglish",
                    "claims": {"agency_name": {"value": "PJ Recruitment", "confidence": "high"}},
                    "safety_flags": [],
                }
            )
        )
        by_type, _ = turn(client, "Galing ako sa PJ Recruitment", session_id=session_id)
        case = by_type["case"]["case"]
        assert case["claims"]["agency_name"]["value"] == "PJ Recruitment"
        # Earlier claims and the safety flag survive the new delta.
        assert case["claims"]["months_unpaid"]["value"] == "3"
        assert "PASSPORT_WITHHELD" in case["safety_flags"]
