"""EMERGENCY path tests (issue #41, ADR-0009 / issue #74): the hardcoded
button opening an Emergency Conversation (zero model calls), at-most-one
live at a time, the DISPATCHER -> EMERGENCY one-way transfer inside it,
mark_safe's latch-only clear, and deleting it while latched — all at the
HTTP seam per tests/test_api.py's fake-injection pattern (fake verifier,
fake model at the BaseLlm boundary, no internals mocked)."""

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
from app.state_keys import EMERGENCY_RESUME
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


def press_button(client, uid="maria") -> tuple[str, list]:
    """Presses the EMERGENCY button; returns (emergency_session_id, lines)."""
    r = client.post("/api/emergency/button", headers=auth(uid))
    assert r.status_code == 200
    lines = [json.loads(line) for line in r.text.splitlines() if line]
    by_type = {line["type"]: line for line in lines}
    return by_type["case"]["session_id"], lines


def open_emergency(client, uid="maria"):
    """Calls the proactive-opener endpoint; returns (status_code, lines)."""
    r = client.post("/api/emergency/opener", headers=auth(uid))
    lines = [json.loads(line) for line in r.text.splitlines() if line]
    return r.status_code, lines


def replay(client, session_id, uid="maria") -> list:
    r = client.get(f"/api/conversations/{session_id}", headers=auth(uid))
    assert r.status_code == 200
    return [json.loads(line) for line in r.text.splitlines() if line]


def mark_safe_nonce(client, uid: str) -> str:
    return client.post("/api/mark-safe/nonce", headers=auth(uid)).json()["nonce"]


def do_mark_safe(client, uid="maria") -> dict:
    nonce = mark_safe_nonce(client, uid)
    r = client.post("/api/mark-safe", json={"nonce": nonce}, headers=auth(uid))
    assert r.status_code == 200
    return r.json()


def conversation_ids(client, uid="maria") -> list[str]:
    r = client.get("/api/conversations", headers=auth(uid))
    return [row["session_id"] for row in r.json()["conversations"]]


def conversation_rows(client, uid="maria") -> list[dict]:
    return client.get("/api/conversations", headers=auth(uid)).json()["conversations"]


class TestHardcodedButtonZeroModelCalls:
    """(1) The hardcoded UI button renders the cached action card OFFLINE
    with ZERO model turns, and opens an Emergency Conversation."""

    def test_button_renders_a_card_with_no_model_calls(self, client, fake_model):
        _, lines = press_button(client)
        by_type = {line["type"]: line for line in lines}
        assert by_type["card"]["card"]["type"] == "safe_floor"
        assert fake_model.calls == []  # ZERO model calls, asserted directly

    def test_button_card_does_not_claim_a_service_outage(self, client):
        # A healthy press is not SERVICE_DOWN: the card must not tell her
        # the app is broken when nothing is.
        _, lines = press_button(client)
        card = {line["type"]: line for line in lines}["card"]["card"]
        assert card["reason"] == "HELP_REQUESTED"
        assert "trouble" not in card["reason_line"].lower()

    def test_button_requires_auth(self, client):
        assert client.post("/api/emergency/button").status_code == 401

    def test_button_opens_an_emergency_conversation_holding_the_latch(
        self, client, fake_model
    ):
        session_id, lines = press_button(client)
        by_type = {line["type"]: line for line in lines}
        assert by_type["emergency_latch"]["active"] is True
        assert by_type["emergency_latch"]["session_id"] == session_id
        # It is a real Conversation in her rail (neutral label, like any).
        assert session_id in conversation_ids(client)
        assert fake_model.calls == []

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


class TestProactiveOpener:
    """(spec 2026-09-06) After the button opens the Conversation, a
    SEPARATE best-effort request has EMERGENCY post one greeting. The
    card path is untouched; a model failure here is swallowed."""

    def test_opener_streams_an_emergency_greeting(self, client, fake_model):
        session_id, _ = press_button(client)

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append(
            "Nandito ako. Gusto mo bang tulungan kitang pag-isipan ang"
            " susunod, o kailangan mo lang ang mga numero?"
        )
        status, lines = open_emergency(client)
        by_type = {line["type"]: line for line in lines}

        assert status == 200
        assert by_type["reply"]["text"] == (
            "Nandito ako. Gusto mo bang tulungan kitang pag-isipan ang"
            " susunod, o kailangan mo lang ang mga numero?"
        )
        assert by_type["reply"]["session_id"] == session_id
        # extraction (before-agent), DISPATCHER transfer, EMERGENCY speaks.
        assert fake_model.calls == ["extraction", "agent", "agent"]

    def test_opener_is_persisted_and_its_trigger_is_never_shown(
        self, client, fake_model
    ):
        from app.emergency import EMERGENCY_OPENER_TRIGGER

        session_id, _ = press_button(client)
        fake_model.extraction_results.append(RuntimeError("nothing"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append("I'm here with you.")
        open_emergency(client)

        transcript = replay(client, session_id)
        replies = [line for line in transcript if line["type"] == "reply"]
        assert any(line["text"] == "I'm here with you." for line in replies)
        # The synthetic stage direction ADK persisted is not her message.
        user_lines = [line for line in transcript if line["type"] == "user"]
        assert all(
            line["text"] != EMERGENCY_OPENER_TRIGGER for line in user_lines
        )

    def test_opener_swallows_a_model_failure(self, client, fake_model):
        session_id, _ = press_button(client)

        fake_model.extraction_results.append(RuntimeError("nothing"))
        fake_model.responses.append(RuntimeError("model down"))
        status, lines = open_emergency(client)

        assert status == 200
        assert not [line for line in lines if line["type"] == "reply"]
        # The Conversation the button opened is still there and latched.
        assert session_id in conversation_ids(client)

    def test_opener_404s_when_no_emergency_conversation_is_live(self, client):
        status, _ = open_emergency(client)
        assert status == 404

    def test_opener_404s_after_mark_safe(self, client):
        press_button(client)
        do_mark_safe(client)
        status, _ = open_emergency(client)
        assert status == 404

    def test_opener_reply_goes_through_the_voice_whitelist(
        self, client, fake_model, caplog
    ):
        import logging

        from app.directory import Country, office_directory_rows

        press_button(client)
        fake_model.extraction_results.append(RuntimeError("nothing"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append(function_call("office_directory", {}))
        fake_model.responses.append("Tumawag ka sa 999 ngayon din.")
        with caplog.at_level(logging.WARNING, logger="app.guard"):
            _, lines = open_emergency(client)

        reply = {line["type"]: line for line in lines}["reply"]["text"]
        assert "999" not in reply
        tool_phones = [row["phone"] for row in office_directory_rows(Country.UNKNOWN)]
        assert any(phone in reply for phone in tool_phones)


class TestAtMostOneLiveEmergencyConversation:
    """(ADR-0009) A second press reopens the existing one; a new one is
    created only after mark_safe has closed the previous."""

    def test_second_press_reopens_the_same_conversation(self, client):
        first, _ = press_button(client)
        second, _ = press_button(client)
        assert first == second
        # A panic double-tap cannot fragment her account across two rows.
        assert conversation_ids(client).count(first) == 1

    def test_latch_line_reports_created_then_reopened(self, client):
        # The frontend fires the proactive opener only on a fresh
        # Emergency Conversation; a second press reopens and must not
        # re-greet.
        _, first_lines = press_button(client)
        _, second_lines = press_button(client)
        first = {line["type"]: line for line in first_lines}
        second = {line["type"]: line for line in second_lines}
        assert first["emergency_latch"]["created"] is True
        assert second["emergency_latch"]["created"] is False

    def test_a_press_after_mark_safe_opens_a_new_conversation(self, client):
        first, _ = press_button(client)
        do_mark_safe(client)
        second, _ = press_button(client)
        assert first != second
        assert set(conversation_ids(client)) == {first, second}

    def test_the_emergency_conversation_never_gets_a_topic_label(
        self, client, fake_model
    ):
        # issue #73/#89 integration: a topic label derived from her shared
        # Case claims would be a disclosure to whoever holds the phone.
        # She first discloses unpaid wages in an ordinary thread (which
        # DOES get a "wages" label), then taps the button.
        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "taglish",
                    "claims": {"months_unpaid": {"value": "6", "confidence": "high"}},
                    "safety_flags": [],
                }
            )
        )
        fake_model.responses.append("Naiintindihan ko.")
        by_type, _ = turn(client, "anim na buwan na akong hindi nababayaran")
        ordinary = by_type["case"]["session_id"]
        emergency, _ = press_button(client)

        rows = {row["session_id"]: row for row in conversation_rows(client)}
        assert rows[ordinary]["label"] == "wages"
        assert rows[emergency]["label"] is None
        assert rows[emergency]["label_source"] is None


class TestEmergencyTransfer:
    """(2) EMERGENCY is the only LLM transfer: DISPATCHER re-transfers
    every turn while the latch is active; exit is a UI tap only."""

    def test_dispatcher_transfers_to_emergency_inside_the_conversation(
        self, client, fake_model
    ):
        session_id, _ = press_button(client)

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append("Nandito ako, kausapin mo ako. Ligtas ka ba ngayon?")
        by_type, _ = turn(client, "tulungan niyo ako", session_id=session_id)
        assert by_type["reply"]["text"] == (
            "Nandito ako, kausapin mo ako. Ligtas ka ba ngayon?"
        )
        assert by_type["emergency_latch"]["active"] is True
        # absorb_narrative's read_narrative runs first, then DISPATCHER's
        # single transfer_to_agent call, then EMERGENCY speaks.
        assert fake_model.calls == ["extraction", "agent", "agent"]

    def test_dispatcher_re_transfers_on_every_subsequent_turn(
        self, client, fake_model
    ):
        session_id, _ = press_button(client)
        for reply in ("Kamusta, ligtas ka ba?", "Sino ang kasama mo ngayon?"):
            fake_model.extraction_results.append(RuntimeError("nothing to read"))
            fake_model.responses.append(transfer_to_emergency())
            fake_model.responses.append(reply)
            by_type, _ = turn(client, "tulong po", session_id=session_id)
            assert by_type["reply"]["text"] == reply

    def test_textual_im_okay_does_not_end_emergency(self, client, fake_model):
        session_id, _ = press_button(client)

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append("Sige, pero sabihin mo sa akin ang totoo.")
        by_type, _ = turn(
            client, "okay lang ako, huwag ka nang mag-alala", session_id=session_id
        )
        # Still EMERGENCY: the latch line is still active, DISPATCHER
        # transferred again rather than speaking in its own voice.
        assert by_type["emergency_latch"]["active"] is True

    def test_her_other_conversations_behave_normally_while_it_is_live(
        self, client, fake_model
    ):
        press_button(client)
        # A separate, ordinary thread (no session_id): no transfer, no
        # latch line — DISPATCHER answers in its own voice.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.responses.append("Kumusta, ano ang pangalan mo?")
        by_type, lines = turn(client, "Hindi ako nababayaran")
        assert by_type["reply"]["text"] == "Kumusta, ano ang pangalan mo?"
        assert "emergency_latch" not in by_type
        assert fake_model.calls == ["extraction", "agent"]


class TestMarkSafeEndsEmergency:
    """(4) mark_safe clears the latch on the ONE live Emergency
    Conversation; DISPATCHER resumes as the voice there next turn — and a
    Safety Flag is never touched."""

    def test_mark_safe_returns_dispatcher_to_the_next_turn(self, client, fake_model):
        session_id, _ = press_button(client)
        assert do_mark_safe(client)["marked_safe"] is True

        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.responses.append("Kumusta, ano ang pangalan mo?")
        by_type, _ = turn(client, "Hindi ako nababayaran", session_id=session_id)
        assert by_type["reply"]["text"] == "Kumusta, ano ang pangalan mo?"
        assert "emergency_latch" not in by_type
        # DISPATCHER's normal turn: extraction, then its own reply — no
        # transfer call was needed.
        assert fake_model.calls == ["extraction", "agent"]

    def test_mark_safe_never_clears_a_safety_flag(self, client, fake_model):
        # She discloses an acute flag in a thread, then taps the button.
        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "taglish",
                    "claims": {},
                    "safety_flags": ["PHYSICAL_ASSAULT_ONGOING"],
                }
            )
        )
        fake_model.responses.append("Narito ako.")
        turn(client, "sinasaktan niya ako ngayon")
        press_button(client)

        result = do_mark_safe(client)
        assert "PHYSICAL_ASSAULT_ONGOING" in result["case"]["safety_flags"]
        assert "emergency" not in result["case"]

    def test_mark_safe_needs_no_conversation_id(self, client):
        # The per-user nonce is the whole identity: no session id in the
        # request body, one unambiguous target via the user-scoped pointer.
        press_button(client)
        nonce = mark_safe_nonce(client, "maria")
        r = client.post("/api/mark-safe", json={"nonce": nonce}, headers=auth("maria"))
        assert r.status_code == 200 and r.json()["marked_safe"] is True


class TestLongGapResume:
    """(4) A long silence while the latch is active re-asks once instead
    of silently resuming deep inside EMERGENCY — HTTP seam."""

    def test_long_silence_gets_one_checkin_reply_not_a_silent_transfer(
        self, client, fake_model
    ):
        session_id, _ = press_button(client)

        # Simulate a long silence: back-date the recorded last_turn_at on
        # the Emergency Conversation's own session state.
        service = client.app.state.chat_service  # type: ignore[attr-defined]
        session = asyncio.run(
            service._session_service.get_session(
                app_name=APP_NAME, user_id="maria", session_id=session_id
            )
        )
        asyncio.run(
            service._session_service.append_event(
                session,
                Event(
                    id=Event.new_id(),
                    invocation_id=f"test-{uuid4().hex}",
                    author="system",
                    actions=EventActions(
                        state_delta={
                            EMERGENCY_RESUME: {
                                "last_turn_at": "2000-01-01T00:00:00+00:00",
                                "resume_check_at": None,
                            }
                        }
                    ),
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
        assert fake_model.calls == ["extraction", "agent"]
        # The latch is untouched: still active, not silently resumed.
        assert by_type["emergency_latch"]["active"] is True

        # The very next turn (short gap, resume check already used):
        # DISPATCHER transfers again as normal.
        fake_model.extraction_results.append(RuntimeError("nothing"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append("Sige, kausapin kita.")
        by_type, _ = turn(client, "opo, kausapin niyo ako", session_id=session_id)
        assert by_type["reply"]["text"] == "Sige, kausapin kita."


class TestDeleteEmergencyConversationWhileLatched:
    """(ADR-0009) Deleting the Emergency Conversation is permitted
    unconditionally, including while the latch is active: it clears the
    latch and the pointer, and her Safety Flags survive on the Case."""

    def test_delete_while_latched_succeeds_and_frees_a_new_press(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(
            json.dumps(
                {
                    "language": "taglish",
                    "claims": {},
                    "safety_flags": ["THREAT_OF_HARM"],
                }
            )
        )
        fake_model.responses.append("Narito ako.")
        turn(client, "pinagbabantaan niya akong saktan")
        first, _ = press_button(client)

        r = client.delete(
            f"/api/conversations/{first}", headers=auth("maria")
        )
        assert r.status_code == 200 and r.json() == {"deleted": True}
        assert first not in conversation_ids(client)

        # A later press opens a FRESH Emergency Conversation instantly.
        second, _ = press_button(client)
        assert second != first
        assert second in conversation_ids(client)

        # Her Safety Flag survived on the Case.
        result = do_mark_safe(client)
        assert "THREAT_OF_HARM" in result["case"]["safety_flags"]


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

        session_id, _ = press_button(client)

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append(function_call("office_directory", {}))
        fake_model.responses.append("Tumawag ka sa 999 ngayon din.")
        with caplog.at_level(logging.WARNING, logger="app.guard"):
            by_type, _ = turn(client, "tulungan niyo ako", session_id=session_id)

        reply = by_type["reply"]["text"]
        assert "999" not in reply
        tool_phones = [row["phone"] for row in office_directory_rows(Country.UNKNOWN)]
        assert tool_phones  # sanity: the fixture actually returned contacts
        assert any(phone in reply for phone in tool_phones)
        assert any(
            "VOICE_WHITELIST miss" in record.getMessage()
            for record in caplog.records
        )
