"""Safe Floor tests (issue #39): pure card fixtures + the HTTP-seam
zero-model hard fallback, per the tests/test_api.py fake-injection
pattern (fake verifier, fake/raising session service, fake model at the
BaseLlm boundary — no internals mocked)."""

import json

import pytest
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field

from app.agent import GEMINI_MODEL
from app.chat import ChatService
from app.directory import Channel, Country
from app.main import create_app
from app.emergency import open_latch
from app.safe_floor import (
    ACUTE_SAFETY_FLAGS,
    CACHED_CARDS,
    CARD_KEYS,
    HOLD_LINE,
    REASON_LINES,
    SafeFloorReason,
    build_card,
    cached_card,
    is_emergency_conversation,
)
from app.state_keys import CASE, EMERGENCY_LATCH
from tests.test_chat_api import FakeVerifier, TAGLISH_EXTRACTION, auth

ALL_CARD_COUNTRIES = list(CARD_KEYS)


class ToolFakeModel(BaseLlm):
    """Fake at the model boundary. ``responses`` entries may be a str
    (DISPATCHER text), a types.Content (e.g. a function_call turn), or an
    Exception (the model is down)."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    responses: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        if llm_request.config and llm_request.config.response_schema is not None:
            self.calls.append("extraction")
            result = self.extraction_results.pop(0)
        else:
            self.calls.append("dispatcher")
            result = self.responses.pop(0) if self.responses else "Nandito ako."
        if isinstance(result, Exception):
            raise result
        if isinstance(result, types.Content):
            yield LlmResponse(content=result)
        else:
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=result)]
                )
            )


def function_call(name: str, args: dict) -> types.Content:
    return types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(name=name, args=args)
            )
        ],
    )


class RaisingSessionService(InMemorySessionService):
    """The session store is down: every method raises."""

    async def create_session(self, **kwargs):
        raise RuntimeError("firestore unavailable")

    async def get_session(self, **kwargs):
        raise RuntimeError("firestore unavailable")


@pytest.fixture()
def fake_model():
    return ToolFakeModel()


def make_client(fake_model, session_service=None):
    service = ChatService(
        session_service=session_service or InMemorySessionService(),
        llm=fake_model,
    )
    return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))


def turn(client, text, *, uid="maria", session_id=None):
    body = {"text": text}
    if session_id is not None:
        body["session_id"] = session_id
    response = client.post("/api/chat", json=body, headers=auth(uid))
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    return lines


class TestCardFixtures:
    @pytest.mark.parametrize("country", ALL_CARD_COUNTRIES)
    def test_every_country_card_is_fixed_and_nonempty(self, country):
        card = build_card(
            country, reason=SafeFloorReason.NO_VERIFIED_PLAN, imminent_danger=False
        )
        assert card["type"] == "safe_floor"
        assert card["contacts"], f"{country} card has no contacts"
        assert card["reason_line"] == REASON_LINES[SafeFloorReason.NO_VERIFIED_PLAN]

    @pytest.mark.parametrize("country", ALL_CARD_COUNTRIES)
    def test_reason_lines_only_from_the_fixed_enum(self, country):
        for reason in SafeFloorReason:
            card = build_card(country, reason=reason, imminent_danger=False)
            assert card["reason_line"] in REASON_LINES.values()

    @pytest.mark.parametrize("country", ALL_CARD_COUNTRIES)
    def test_hold_line_present_normally_suppressed_under_danger(self, country):
        calm = build_card(
            country, reason=SafeFloorReason.NO_VERIFIED_PLAN, imminent_danger=False
        )
        danger = build_card(
            country, reason=SafeFloorReason.NO_VERIFIED_PLAN, imminent_danger=True
        )
        assert calm["hold_line"] == HOLD_LINE
        assert danger["hold_line"] is None

    @pytest.mark.parametrize(
        "country", [Country.SA, Country.QA, Country.KW, Country.AE]
    )
    def test_ph_short_codes_never_dialable_from_the_gulf(self, country):
        card = build_card(
            country, reason=SafeFloorReason.NO_VERIFIED_PLAN, imminent_danger=False
        )
        for contact in card["contacts"]:
            # A bare PH short code (no international prefix) must never
            # render as if she could dial it from the Gulf.
            if not contact["phone"].startswith("+"):
                assert contact["dial_mode"] == "manila_relay", contact
            if contact["channel"] == Channel.OWWA_1348.value:
                assert contact["dial_mode"] == "manila_relay", contact

    @pytest.mark.parametrize(
        "country", [Country.SA, Country.QA, Country.KW, Country.AE]
    )
    def test_mwo_and_embassy_are_dialable_international_format(self, country):
        card = build_card(
            country, reason=SafeFloorReason.NO_VERIFIED_PLAN, imminent_danger=False
        )
        primary = [
            contact
            for contact in card["contacts"]
            if contact["channel"]
            in (Channel.MWO.value, Channel.EMBASSY_ATN.value)
            and contact["dial_mode"] == "dialable"
        ]
        assert primary, f"{country}: no dialable MWO/embassy row"
        for contact in primary:
            assert contact["phone"].startswith("+"), contact

    def test_unknown_country_card_is_embassy_atn_and_1348_only(self):
        card = build_card(
            Country.UNKNOWN,
            reason=SafeFloorReason.NO_VERIFIED_PLAN,
            imminent_danger=False,
        )
        channels = {contact["channel"] for contact in card["contacts"]}
        assert channels <= {Channel.EMBASSY_ATN.value, Channel.OWWA_1348.value}
        assert channels

    def test_cache_is_precomputed_for_every_country_and_danger_state(self):
        for country in ALL_CARD_COUNTRIES:
            for danger in (False, True):
                assert (country, danger) in CACHED_CARDS
        assert cached_card(Country("SA"))["country"] == "SA"
        # Unreadable country falls back to UNKNOWN, never KeyErrors.
        assert cached_card(Country.PH)["country"] == "UNKNOWN"


class TestImminentDangerPredicate:
    """Integration-level checks that Safe Floor's predicate hook is the
    real one from app.emergency — "this Conversation is the Emergency
    one", read off the Conversation latch (ADR-0009). The exhaustive
    pure suite lives in tests/test_emergency_latch.py."""

    def test_latch_active_state_is_emergency(self):
        assert is_emergency_conversation(
            {EMERGENCY_LATCH: open_latch(now="2024-01-01T00:00:00Z")}
        ) is True

    def test_a_flag_on_the_case_alone_is_not_an_emergency_conversation(self):
        from app.case import merge_case

        case = merge_case(
            None,
            {"safety_flags": ["PHYSICAL_ASSAULT_ONGOING"]},
            now="2024-01-01T00:00:00Z",
        )
        # A disclosure records a Pending Escalation; it does NOT make the
        # Conversation the Emergency one.
        assert is_emergency_conversation({CASE: case}) is False

    def test_no_state_is_not_an_emergency_conversation(self):
        assert is_emergency_conversation(None) is False
        assert is_emergency_conversation({}) is False

    def test_acute_set_is_a_frozenset_in_code(self):
        assert isinstance(ACUTE_SAFETY_FLAGS, frozenset)
        assert "PHYSICAL_ASSAULT_ONGOING" in ACUTE_SAFETY_FLAGS
        assert "PHYSICAL_ASSAULT_PAST" not in ACUTE_SAFETY_FLAGS

    def test_safe_floor_card_tool_suppresses_hold_line_in_an_emergency_conversation(
        self,
    ):
        """End-to-end through app.tools.safe_floor_card: the hold_line is
        suppressed only when THIS Conversation holds the latch, not merely
        because an acute flag is on her Case."""
        from app.case import merge_case
        from app.tools import safe_floor_card

        class FakeToolContext:
            def __init__(self, state):
                self.state = state

        case = merge_case(
            None,
            {
                "claims": {"country": {"value": "Saudi Arabia", "confidence": "high"}},
                "safety_flags": ["PHYSICAL_ASSAULT_ONGOING"],
            },
            now="2024-01-01T00:00:00Z",
        )
        # A normal Conversation: acute flag on the Case, but no latch.
        result = safe_floor_card("NO_VERIFIED_PLAN", FakeToolContext({CASE: case}))
        assert result["card"]["hold_line"] == HOLD_LINE

        # The Emergency Conversation: latch active -> hold_line suppressed.
        result = safe_floor_card(
            "NO_VERIFIED_PLAN",
            FakeToolContext(
                {CASE: case, EMERGENCY_LATCH: open_latch(now="2024-01-01T00:05:00Z")}
            ),
        )
        assert result["card"]["hold_line"] is None


class TestHardFallbackHttpSeam:
    def test_store_down_renders_cached_card_with_zero_model_calls(
        self, fake_model
    ):
        client = make_client(fake_model, session_service=RaisingSessionService())
        lines = turn(client, "tulong po")
        by_type = {line["type"]: line for line in lines}
        assert by_type["card"]["card"]["type"] == "safe_floor"
        assert by_type["card"]["card"]["reason"] == "SERVICE_DOWN"
        assert "error" in by_type  # surfaced, not swallowed
        assert fake_model.calls == []  # ZERO model calls

    def test_model_down_mid_turn_renders_cached_card_for_her_country(
        self, fake_model
    ):
        client = make_client(fake_model)
        # Turn 1 seeds the case (country: Saudi Arabia).
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.responses.append("Kumusta ka?")
        lines = turn(client, "Hindi ako nababayaran, nasa Saudi ako")
        session_id = lines[-1]["session_id"]

        # Turn 2: extractor AND model down.
        fake_model.extraction_results.append(RuntimeError("model down"))
        fake_model.responses.append(RuntimeError("model down"))
        lines = turn(client, "tulong", session_id=session_id)
        by_type = {line["type"]: line for line in lines}
        card = by_type["card"]["card"]
        assert card["type"] == "safe_floor"
        assert card["country"] == "SA"
        assert card["reason"] == "SERVICE_DOWN"
        assert "error" in by_type


class TestBoundedOutcomeViaDispatcher:
    def test_safe_floor_tool_turn_streams_the_fixed_card(self, fake_model):
        """Demoable: with no verified Plan available, she sees her
        country's Safe Floor card with a hand-written reason line."""
        client = make_client(fake_model)
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.responses.append(
            function_call("safe_floor_card", {"reason": "NO_VERIFIED_PLAN"})
        )
        fake_model.responses.append(
            "Hindi pa ako sigurado sa tamang pagkakasunod — narito ang mga"
            " totoong opisina."
        )
        lines = turn(client, "Ano ang unang hakbang ko?")
        cards = [line for line in lines if line["type"] == "card"]
        assert len(cards) == 1
        card = cards[0]["card"]
        assert card["type"] == "safe_floor"
        assert card["country"] == "SA"
        assert card["reason_line"] == REASON_LINES[SafeFloorReason.NO_VERIFIED_PLAN]
        assert card["contacts"]

    def test_unknown_country_tool_turn_gets_restricted_card(self, fake_model):
        client = make_client(fake_model)
        fake_model.extraction_results.append(
            json.dumps(
                {"language": "tl", "claims": {}, "safety_flags": []}
            )
        )
        fake_model.responses.append(
            function_call("safe_floor_card", {"reason": "NO_VERIFIED_PLAN"})
        )
        fake_model.responses.append("Narito ang matatawagan mo.")
        lines = turn(client, "tulungan mo ako")
        card = next(line for line in lines if line["type"] == "card")["card"]
        assert card["country"] == "UNKNOWN"
        channels = {contact["channel"] for contact in card["contacts"]}
        assert channels <= {Channel.EMBASSY_ATN.value, Channel.OWWA_1348.value}
