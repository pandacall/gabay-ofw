"""EMERGENCY path tests (issue #41): the hardcoded button (zero model
calls), the DISPATCHER -> EMERGENCY one-way transfer, and mark_safe's
predicate-only clear, at the HTTP seam per tests/test_api.py's
fake-injection pattern (fake verifier, fake model at the BaseLlm
boundary — no internals mocked)."""

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.adk.events import Event, EventActions
from google.adk.models import BaseLlm, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field

from app.agent import APP_NAME, GEMINI_MODEL
from app.chat import ChatService
from app.main import create_app
from tests.test_chat_api import TAGLISH_EXTRACTION


class ScriptedModel(BaseLlm):
    """Fake at the model boundary. ``responses`` entries may be a str
    (agent text) or a types.Content (e.g. a transfer_to_agent function
    call)."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    responses: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        if llm_request.config and llm_request.config.response_schema is not None:
            self.calls.append("extraction")
            result = self.extraction_results.pop(0)
        else:
            self.calls.append("agent")
            result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, types.Content):
            yield LlmResponse(content=result)
        else:
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
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


def function_call(name: str, args: dict) -> types.Content:
    return types.Content(
        role="model",
        parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))],
    )


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


@pytest.fixture()
def fake_model():
    return ScriptedModel()


@pytest.fixture()
def client(fake_model):
    service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
    return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))


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


def mark_safe_nonce(client, uid: str) -> str:
    return client.post("/api/mark-safe/nonce", headers=auth(uid)).json()["nonce"]


class TestHardcodedButtonZeroModelCalls:
    """(1) The hardcoded UI button renders the cached action card OFFLINE
    with ZERO model turns."""

    def test_button_renders_a_card_with_no_model_calls(self, client, fake_model):
        r = client.post("/api/emergency/button", headers=auth("maria"))
        assert r.status_code == 200
        lines = [json.loads(line) for line in r.text.splitlines() if line]
        by_type = {line["type"]: line for line in lines}
        assert by_type["card"]["card"]["type"] == "safe_floor"
        assert fake_model.calls == []  # ZERO model calls, asserted directly

    def test_button_requires_auth(self, client):
        assert client.post("/api/emergency/button").status_code == 401

    def test_button_trips_the_predicate_for_the_next_turn(self, client, fake_model):
        r = client.post("/api/emergency/button", headers=auth("maria"))
        case = json.loads(
            [line for line in r.text.splitlines() if line][-1]
        )["case"]
        assert case["emergency"]["active"] is True

    def test_button_still_renders_the_card_when_the_session_store_is_down(
        self, fake_model
    ):
        # PRD #34 user story 28: "help survives a dead model, a dead
        # session store, or a dead connection" — the card must not be
        # gated on the session store succeeding.
        class RaisingSessionService(InMemorySessionService):
            async def list_sessions(self, **kwargs):
                raise RuntimeError("firestore unavailable")

            async def create_session(self, **kwargs):
                raise RuntimeError("firestore unavailable")

        service = ChatService(
            session_service=RaisingSessionService(), llm=fake_model
        )
        client = TestClient(
            create_app(verifier=FakeVerifier(), chat_service=service)
        )
        r = client.post("/api/emergency/button", headers=auth("maria"))
        assert r.status_code == 200
        lines = [json.loads(line) for line in r.text.splitlines() if line]
        by_type = {line["type"]: line for line in lines}
        assert by_type["card"]["card"]["type"] == "safe_floor"
        assert "error" in by_type  # surfaced, not swallowed
        assert fake_model.calls == []


class TestEmergencyTransfer:
    """(2) EMERGENCY is the only LLM transfer: DISPATCHER re-transfers
    every turn while the predicate is active; exit is a UI tap only."""

    def test_dispatcher_transfers_to_emergency_when_predicate_active(
        self, client, fake_model
    ):
        client.post("/api/emergency/button", headers=auth("maria"))

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append("Nandito ako, kausapin mo ako. Ligtas ka ba ngayon?")
        by_type, _ = turn(client, "tulungan niyo ako")
        assert by_type["reply"]["text"] == (
            "Nandito ako, kausapin mo ako. Ligtas ka ba ngayon?"
        )
        # absorb_narrative's read_narrative always runs first (root
        # before-agent callback, per app.agent); then DISPATCHER's own
        # turn is exactly one transfer_to_agent call, then EMERGENCY
        # speaks.
        assert fake_model.calls == ["extraction", "agent", "agent"]

    def test_dispatcher_re_transfers_on_every_subsequent_turn(
        self, client, fake_model
    ):
        session = None
        client.post("/api/emergency/button", headers=auth("maria"))

        for reply in ("Kamusta, ligtas ka ba?", "Sino ang kasama mo ngayon?"):
            fake_model.responses.append(transfer_to_emergency())
            fake_model.responses.append(reply)
            by_type, _ = turn(client, "tulong po", session_id=session)
            session = by_type["reply"]["session_id"]
            assert by_type["reply"]["text"] == reply

    def test_textual_im_okay_does_not_end_emergency(self, client, fake_model):
        button = client.post("/api/emergency/button", headers=auth("maria"))
        session_id = json.loads(
            [line for line in button.text.splitlines() if line][-1]
        )["session_id"]

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append("Sige, pero sabihin mo sa akin ang totoo.")
        by_type, _ = turn(
            client,
            "okay lang ako, huwag ka nang mag-alala",
            session_id=session_id,
        )
        # Still EMERGENCY: DISPATCHER transferred again, not its own voice.
        assert "case" in by_type
        assert by_type["case"]["case"]["emergency"]["active"] is True


class TestMarkSafeEndsEmergency:
    """(4) mark_safe clears the predicate; DISPATCHER resumes as the
    voice on the next turn."""

    def test_mark_safe_returns_dispatcher_to_the_next_turn(self, client, fake_model):
        client.post("/api/emergency/button", headers=auth("maria"))
        nonce = mark_safe_nonce(client, "maria")
        r = client.post(
            "/api/mark-safe", json={"nonce": nonce}, headers=auth("maria")
        )
        assert r.status_code == 200
        assert r.json()["case"]["emergency"]["active"] is False

        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.responses.append("Kumusta, ano ang pangalan mo?")
        by_type, _ = turn(client, "Hindi ako nababayaran")
        assert by_type["reply"]["text"] == "Kumusta, ano ang pangalan mo?"
        # DISPATCHER's normal turn: extraction, then its own reply — no
        # transfer call was needed.
        assert fake_model.calls == ["extraction", "agent"]


class TestLongGapResume:
    """(4) A long silence while the predicate is active re-asks once
    instead of silently resuming deep inside EMERGENCY — HTTP seam."""

    def test_long_silence_gets_one_checkin_reply_not_a_silent_transfer(
        self, client, fake_model
    ):
        button = client.post("/api/emergency/button", headers=auth("maria"))
        session_id = json.loads(
            [line for line in button.text.splitlines() if line][-1]
        )["session_id"]

        # Simulate a long silence: back-date the recorded last_turn_at
        # directly on the session's Case, the same way a real Firestore
        # session would carry it forward across a real gap.
        service = client.app.state.chat_service  # type: ignore[attr-defined]
        session = asyncio.run(
            service._session_service.get_session(
                app_name=APP_NAME, user_id="maria", session_id=session_id
            )
        )
        stale_case = dict(session.state["case"])
        stale_case["emergency"] = dict(stale_case["emergency"])
        stale_case["emergency"]["last_turn_at"] = "2000-01-01T00:00:00+00:00"
        asyncio.run(
            service._session_service.append_event(
                session,
                Event(
                    id=Event.new_id(),
                    invocation_id=f"test-{uuid4().hex}",
                    author="system",
                    actions=EventActions(state_delta={"case": stale_case}),
                ),
            )
        )

        # No transfer_to_emergency() queued: if DISPATCHER transferred
        # instead of checking in, ScriptedModel would pop the wrong
        # fixture and the reply assertion below would fail.
        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(
            "Kumusta ka na? Matagal na tayong hindi nag-usap — ligtas ka ba ngayon?"
        )
        by_type, _ = turn(client, "hello po", session_id=session_id)
        assert by_type["reply"]["text"] == (
            "Kumusta ka na? Matagal na tayong hindi nag-usap — ligtas ka ba ngayon?"
        )
        # Exactly one model call for DISPATCHER's own check-in reply — no
        # transfer_to_agent call this turn.
        assert fake_model.calls == ["extraction", "agent"]
        # The predicate is untouched: still active, not silently resumed.
        assert by_type["case"]["case"]["emergency"]["active"] is True

        # The very next turn (short gap, resume check already used):
        # DISPATCHER transfers again as normal.
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append("Sige, kausapin kita.")
        by_type, _ = turn(client, "opo, kausapin niyo ako", session_id=session_id)
        assert by_type["reply"]["text"] == "Sige, kausapin kita."


class TestEmergencyVoiceWhitelist:
    """EMERGENCY converses freely just like DISPATCHER, so the same
    after-model whitelist diff (ROUTING_GUARD, issue #39) must apply to
    her replies too — a fabricated contact number must not slip through
    just because a transfer, not the root turn, handed her the
    conversation."""

    def test_emergency_fabricated_number_is_replaced_and_logged(
        self, client, fake_model, caplog
    ):
        import logging

        from app.directory import Country, office_directory_rows

        client.post("/api/emergency/button", headers=auth("maria"))

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append(function_call("office_directory", {}))
        fake_model.responses.append("Tumawag ka sa 999 ngayon din.")
        with caplog.at_level(logging.WARNING, logger="app.guard"):
            by_type, _ = turn(client, "tulungan niyo ako")

        reply = by_type["reply"]["text"]
        assert "999" not in reply
        tool_phones = [row["phone"] for row in office_directory_rows(Country.UNKNOWN)]
        assert tool_phones  # sanity: the fixture actually returned contacts
        assert any(phone in reply for phone in tool_phones)
        assert any(
            "VOICE_WHITELIST miss" in record.getMessage()
            for record in caplog.records
        )
