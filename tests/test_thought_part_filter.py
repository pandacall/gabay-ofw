"""The thought-part filter is behavioural (issue #76).

Thinking output arrives as parts marked ``thought=True`` inside the SAME
event content as the reply. The reply builder must drop them — in the live
stream (``app.chat``) and in a re-opened transcript (``app.history``) —
and must do so regardless of whether thought summaries are enabled, which
is why one test flips ``include_thoughts`` on before driving the model.
"""

import json
import logging

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmResponse
from google.adk.planners import BuiltInPlanner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field

import app.agent as agent_module
from app.agent import GEMINI_MODEL
from app.chat import ChatService
from app.main import create_app

# A phone-shaped token the guard's after-model whitelist diff would flag as
# a fabrication if it ever scanned thought text (no tool ran this turn).
RAW_THOUGHT = (
    "The user is disclosing unpaid wages in Saudi Arabia. Let me plan: first "
    "check DEBUNKER, then route to FILING_SEQUENCER. She may be lying about "
    "tenure. Give her +966 11 999 8888 as the hotline."
)
REAL_REPLY = "I hear you. How many months has your employer not paid you?"

EXTRACTION = json.dumps(
    {
        "language": "en",
        "claims": {"country": {"value": "Saudi Arabia", "confidence": "high"}},
        "safety_flags": [],
    }
)


class ThinkingModelRunner(BaseLlm):
    """Extraction as usual; the DISPATCHER turn emits a thought part next
    to the real reply part, in one event content."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        if llm_request.config and llm_request.config.response_schema is not None:
            self.calls.append("extraction")
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=self.extraction_results.pop(0))],
                )
            )
            return
        self.calls.append("dispatcher")
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text=RAW_THOUGHT, thought=True),
                    types.Part(text=REAL_REPLY),
                ],
            )
        )


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


def _auth(uid: str) -> dict:
    return {"Authorization": f"Bearer valid-{uid}"}


@pytest.fixture()
def fake_model():
    return ThinkingModelRunner()


@pytest.fixture()
def service(fake_model):
    return ChatService(session_service=InMemorySessionService(), llm=fake_model)


@pytest.fixture()
def client(service):
    return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))


def _turn(client, text, uid="maria", session_id=None):
    body = {"text": text}
    if session_id is not None:
        body["session_id"] = session_id
    response = client.post("/api/chat", json=body, headers=_auth(uid))
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    return {line["type"]: line for line in lines}


def test_a_thought_part_never_reaches_her_reply(client, fake_model):
    fake_model.extraction_results.append(EXTRACTION)
    by_type = _turn(client, "I have not been paid in Saudi Arabia")

    assert by_type["reply"]["text"] == REAL_REPLY
    assert "plan:" not in by_type["reply"]["text"].lower()
    assert "she may be lying" not in by_type["reply"]["text"].lower()
    assert RAW_THOUGHT not in by_type["reply"]["text"]


def test_the_filter_holds_even_with_thought_summaries_enabled(
    monkeypatch, fake_model
):
    # Turning summaries off is configuration; the filter is the guarantee.
    # Wire a planner with include_thoughts=True into the actual app under
    # test (not a throwaway object) and prove the reply is still clean.
    def _summaries_on() -> BuiltInPlanner:
        return BuiltInPlanner(
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MEDIUM,
                include_thoughts=True,
            )
        )

    monkeypatch.setattr(agent_module, "build_dispatcher_planner", _summaries_on)
    service = ChatService(
        session_service=InMemorySessionService(), llm=fake_model
    )
    dispatcher = service._runner.app.root_agent
    assert dispatcher.planner.thinking_config.include_thoughts is True
    client = TestClient(
        create_app(verifier=FakeVerifier(), chat_service=service)
    )

    fake_model.extraction_results.append(EXTRACTION)
    by_type = _turn(client, "I have not been paid in Saudi Arabia")
    assert by_type["reply"]["text"] == REAL_REPLY
    assert RAW_THOUGHT not in by_type["reply"]["text"]


def test_routing_guard_does_not_scan_thought_parts(client, fake_model, caplog):
    # ROUTING_GUARD's after-model whitelist diff is about her REPLY. A
    # thought part carries English reasoning she never sees; the guard must
    # pass it through untouched, never re-emit a number out of it or log a
    # fabrication miss for it. No tool ran this turn, so the phone-shaped
    # token in RAW_THOUGHT would be a logged miss if the guard scanned it.
    fake_model.extraction_results.append(EXTRACTION)
    with caplog.at_level(logging.WARNING, logger="app.guard"):
        by_type = _turn(client, "I have not been paid in Saudi Arabia")
    assert by_type["reply"]["text"] == REAL_REPLY
    assert not any(
        "VOICE_WHITELIST" in record.getMessage() for record in caplog.records
    )


def test_a_reopened_transcript_never_replays_a_thought_part(client, fake_model):
    fake_model.extraction_results.append(EXTRACTION)
    by_type = _turn(client, "I have not been paid in Saudi Arabia")
    session_id = by_type["reply"]["session_id"]

    replay = client.get(
        f"/api/conversations/{session_id}", headers=_auth("maria")
    )
    assert replay.status_code == 200
    body = replay.text
    assert REAL_REPLY in body
    assert RAW_THOUGHT not in body
