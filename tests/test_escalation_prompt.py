"""The Escalation Prompt and the Escalation Handoff (ADR-0009, issue #74),
at the HTTP seam — one test per acceptance criterion. Same fake-injection
pattern as tests/test_chat_api.py (fake verifier, fake model at the
BaseLlm boundary, InMemory sessions, nothing internal mocked).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field

from app.agent import APP_NAME, GEMINI_MODEL
from app.chat import ChatService
from app.main import create_app
from app.state_keys import EMERGENCY_CONVERSATION_ID_RAW, ESCALATION_HANDOFF
from tests.test_emergency import FakeVerifier, auth, transfer_to_emergency


class ScriptedModel(BaseLlm):
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
            result = self.responses.pop(0) if self.responses else "Narito ako."
        if isinstance(result, Exception):
            raise result
        if isinstance(result, types.Content):
            yield LlmResponse(content=result)
        else:
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
            )


@pytest.fixture()
def fake_model():
    return ScriptedModel()


@pytest.fixture()
def service(fake_model):
    return ChatService(session_service=InMemorySessionService(), llm=fake_model)


@pytest.fixture()
def client(service):
    return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))


def extraction(*flags: str, language: str = "taglish", claims: dict | None = None) -> str:
    return json.dumps(
        {"language": language, "claims": claims or {}, "safety_flags": list(flags)}
    )


def turn(client, text, *, uid="maria", session_id=None):
    body = {"text": text}
    if session_id is not None:
        body["session_id"] = session_id
    r = client.post("/api/chat", json=body, headers=auth(uid))
    assert r.status_code == 200
    lines = [json.loads(line) for line in r.text.splitlines() if line]
    return {line["type"]: line for line in lines}, lines


SA_CLAIM = {"country": {"value": "Saudi Arabia", "confidence": "high"}}


class TestAcuteDisclosureShowsThePromptAndTransfersNobody:
    def test_disclosure_records_pending_escalation_and_prompts_without_transfer(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(
            extraction("PHYSICAL_ASSAULT_ONGOING", claims=SA_CLAIM)
        )
        fake_model.responses.append("Narinig kita. Nandito ako.")
        by_type, lines = turn(client, "sinasaktan niya ako ngayon")

        # No transfer: exactly extraction + one DISPATCHER reply.
        assert fake_model.calls == ["extraction", "agent"]
        assert "emergency_latch" not in by_type
        # Pending Escalation on the Case.
        assert by_type["case"]["case"]["pending_escalation"]["flag"] == (
            "PHYSICAL_ASSAULT_ONGOING"
        )
        # The Escalation Prompt line, carrying the source Conversation id.
        prompt = by_type["escalation_prompt"]["escalation_prompt"]
        assert prompt["reason_category"] == "ASSAULT"
        assert prompt["source_session_id"] == by_type["case"]["session_id"]
        assert prompt["country"] == "SA"

    def test_the_safe_floor_card_renders_at_the_same_time_as_the_prompt(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(
            extraction("THREAT_OF_HARM", claims=SA_CLAIM)
        )
        fake_model.responses.append("Narito ako.")
        _, lines = turn(client, "pinagbabantaan niya akong patayin")

        types_in_order = [line["type"] for line in lines]
        card_idx = next(
            i
            for i, line in enumerate(lines)
            if line["type"] == "card"
            and line["card"].get("reason") == "ACUTE_DISCLOSURE"
        )
        prompt_idx = types_in_order.index("escalation_prompt")
        # The card comes WITH the prompt, immediately before it — not after.
        assert card_idx < prompt_idx
        card = lines[card_idx]["card"]
        assert card["type"] == "safe_floor"
        assert card["country"] == "SA"
        assert card["contacts"]
        # Leaving may be exactly right under acute danger: no stay-put line.
        assert card["hold_line"] is None

    def test_chronic_flag_alone_shows_no_prompt(self, client, fake_model):
        fake_model.extraction_results.append(extraction("PASSPORT_WITHHELD"))
        fake_model.responses.append("Salamat sa pagbabahagi.")
        by_type, _ = turn(client, "kinuha nila ang passport ko")
        assert "escalation_prompt" not in by_type
        assert by_type["case"]["case"]["pending_escalation"] is None


class TestDecliningDismissesThePromptNeverTheFlag:
    def test_declining_is_client_only_and_keeps_the_flag_and_provenance(
        self, client, service, fake_model
    ):
        fake_model.extraction_results.append(extraction("THREAT_OF_HARM"))
        fake_model.responses.append("Narito ako.")
        by_type, _ = turn(client, "sinabi niyang sasaktan niya ako")
        # She declines: no /api/emergency/escalate call at all.

        case = by_type["case"]["case"]
        assert "THREAT_OF_HARM" in case["safety_flags"]
        assert case["safety_flags"]["THREAT_OF_HARM"]["source"] == "extraction"
        # No Emergency Conversation was created.
        user_state = asyncio.run(
            service._session_service.get_user_state(
                app_name=APP_NAME, user_id="maria"
            )
        )
        assert user_state.get(EMERGENCY_CONVERSATION_ID_RAW) is None

    def test_same_hazard_does_not_re_prompt_but_a_different_one_does(
        self, client, fake_model
    ):
        # Turn 1: acute flag A -> prompt.
        fake_model.extraction_results.append(extraction("THREAT_OF_HARM"))
        fake_model.responses.append("Narito ako.")
        by_type, _ = turn(client, "pinagbabantaan niya ako")
        session_id = by_type["case"]["session_id"]
        assert "escalation_prompt" in by_type

        # Turn 2: the SAME flag surfaces again -> no re-prompt (add-only:
        # the flag is not new).
        fake_model.extraction_results.append(extraction("THREAT_OF_HARM"))
        fake_model.responses.append("Naiintindihan ko.")
        by_type, _ = turn(client, "uli niyang binanta ako", session_id=session_id)
        assert "escalation_prompt" not in by_type

        # Turn 3: a DIFFERENT acute flag -> prompts again.
        fake_model.extraction_results.append(extraction("PHYSICAL_ASSAULT_ONGOING"))
        fake_model.responses.append("Narinig kita.")
        by_type, _ = turn(client, "ngayon sinasaktan na niya ako", session_id=session_id)
        assert "escalation_prompt" in by_type
        assert by_type["escalation_prompt"]["escalation_prompt"]["reason_category"] == (
            "ASSAULT"
        )


class TestConfirmingOpensTheEmergencyConversation:
    def _disclose(self, client, fake_model) -> str:
        fake_model.extraction_results.append(
            extraction("PHYSICAL_ASSAULT_ONGOING", claims=SA_CLAIM)
        )
        fake_model.responses.append("Narito ako.")
        by_type, _ = turn(client, "sinasaktan niya ako ngayon")
        return by_type["escalation_prompt"]["escalation_prompt"]["source_session_id"]

    def test_confirm_opens_a_new_conversation_with_the_handoff(
        self, client, service, fake_model
    ):
        source = self._disclose(client, fake_model)
        source_transcript_before = client.get(
            f"/api/conversations/{source}", headers=auth("maria")
        ).text

        r = client.post(
            "/api/emergency/escalate",
            json={"source_session_id": source},
            headers=auth("maria"),
        )
        assert r.status_code == 200
        emergency_id = r.json()["emergency_session_id"]
        assert emergency_id != source

        # The Emergency Conversation holds the latch: a turn there
        # transfers to EMERGENCY.
        fake_model.extraction_results.append(json.dumps({"language": "taglish", "claims": {}, "safety_flags": []}))
        fake_model.responses.append(transfer_to_emergency())
        fake_model.responses.append("Nandito ako. Ligtas ka ba ngayon?")
        by_type, _ = turn(client, "hello", session_id=emergency_id)
        assert by_type["reply"]["text"] == "Nandito ako. Ligtas ka ba ngayon?"
        assert by_type["emergency_latch"]["active"] is True

        # The source Conversation is exactly as it was — escalate never
        # wrote to it.
        source_transcript_after = client.get(
            f"/api/conversations/{source}", headers=auth("maria")
        ).text
        assert source_transcript_after == source_transcript_before

    def test_the_handoff_carries_facts_never_the_transcript(
        self, client, service, fake_model
    ):
        source = self._disclose(client, fake_model)
        r = client.post(
            "/api/emergency/escalate",
            json={"source_session_id": source},
            headers=auth("maria"),
        )
        emergency_id = r.json()["emergency_session_id"]
        emergency_session = asyncio.run(
            service._session_service.get_session(
                app_name=APP_NAME, user_id="maria", session_id=emergency_id
            )
        )
        handoff = emergency_session.state[ESCALATION_HANDOFF]
        assert set(handoff) == {
            "country",
            "reason_category",
            "summary",
            "source_session_id",
        }
        assert handoff["country"] == "SA"
        assert handoff["reason_category"] == "ASSAULT"
        assert handoff["source_session_id"] == source
        # Nothing she typed is anywhere in the handoff.
        assert "sinasaktan niya ako ngayon" not in json.dumps(
            handoff, ensure_ascii=False
        )

    def test_the_emergency_conversation_already_knows_her_case(
        self, client, service, fake_model
    ):
        from app.agent import _emergency_instruction

        source = self._disclose(client, fake_model)
        r = client.post(
            "/api/emergency/escalate",
            json={"source_session_id": source},
            headers=auth("maria"),
        )
        emergency_session = asyncio.run(
            service._session_service.get_session(
                app_name=APP_NAME,
                user_id="maria",
                session_id=r.json()["emergency_session_id"],
            )
        )

        class _Ctx:
            def __init__(self, state):
                self.state = state

        instruction = _emergency_instruction(_Ctx(emergency_session.state))
        # It opens knowing her Case AND the handoff, and is told not to
        # re-ask what she disclosed under duress.
        assert "Saudi Arabia" in instruction
        assert "do NOT re-ask" in instruction
        assert "Escalation Handoff" in instruction

    def test_confirming_twice_reopens_rather_than_forking(
        self, client, fake_model
    ):
        source = self._disclose(client, fake_model)
        first = client.post(
            "/api/emergency/escalate",
            json={"source_session_id": source},
            headers=auth("maria"),
        ).json()["emergency_session_id"]
        second = client.post(
            "/api/emergency/escalate",
            json={"source_session_id": source},
            headers=auth("maria"),
        ).json()["emergency_session_id"]
        assert first == second

    def test_unknown_source_conversation_is_404(self, client):
        r = client.post(
            "/api/emergency/escalate",
            json={"source_session_id": "nope"},
            headers=auth("maria"),
        )
        assert r.status_code == 404

    def test_another_users_source_conversation_is_404(self, client, fake_model):
        source = self._disclose(client, fake_model)
        r = client.post(
            "/api/emergency/escalate",
            json={"source_session_id": source},
            headers=auth("intruder"),
        )
        assert r.status_code == 404
