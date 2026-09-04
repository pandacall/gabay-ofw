"""Progress Trail behavioral tests (issue #75, ADR-0010).

Two layers, mirroring the ADR's own testing note:

* Unit tests directly on the fixed label table (``app.agent``) — no
  model, no HTTP — asserting the table's WORDING never names a tool, an
  agent, or looks like JSON, and that the closed language set/normalization
  matches ``acknowledgement_for`` exactly.
* HTTP-seam tests at ``/api/chat``, in the same style as
  ``tests/test_chat_api.py`` and ``tests/test_debunker_http.py``: a
  scripted fake model at the ADK ``BaseLlm`` boundary, no internals
  mocked, asserting on the resulting NDJSON ``trail`` lines only.
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

from app.agent import (
    ACKNOWLEDGEMENTS,
    GEMINI_MODEL,
    PROGRESS_TRAIL_LABELS,
    PROGRESS_TRAIL_OPENING,
    progress_trail_label_for,
    progress_trail_opening_for,
)
from app.chat import ChatService
from app.main import create_app

TAGLISH_EXTRACTION = json.dumps(
    {
        "language": "taglish",
        "claims": {"country": {"value": "Saudi Arabia", "confidence": "high"}},
        "safety_flags": [],
    }
)

CEB_EXTRACTION = json.dumps(
    {
        "language": "ceb",
        "claims": {"country": {"value": "Saudi Arabia", "confidence": "high"}},
        "safety_flags": [],
    }
)

ENGLISH_EXTRACTION = json.dumps(
    {
        "language": "en",
        "claims": {"country": {"value": "Saudi Arabia", "confidence": "high"}},
        "safety_flags": [],
    }
)

DISPATCHER_REPLY = "Narito ako para tumulong."


# ---------------------------------------------------------------------------
# Unit tests on the fixed table itself — no model, no HTTP.
# ---------------------------------------------------------------------------


#: Every raw tool/agent name the table's CALLERS may key on. A label's
#: WORDING must never contain one of these verbatim — that would be a raw
#: tool/agent name on screen, the exact failure mode ADR-0010 forbids.
_RAW_NAMES = (
    "DEBUNKER",
    "PROOF_BUILDER",
    "FILING_SEQUENCER",
    "COMPLAINT_DRAFTER",
    "RECOURSE_ROUTER",
    "search_corpus",
    "sequencer_jurisdiction_rules",
    "sequencer_sequence_actions",
    "sequencer_compute_deadlines",
    "sequencer_verify_plan",
    "complaint_check_agency_license",
    "complaint_check_safe_to_file",
    "complaint_prepare_form",
    "complaint_review_and_finalize",
    "recourse_build_routes",
)

#: Words that would turn a task label into a hypothesis/accusation about
#: her situation — the ADR-0010 wording rule ("Looking up your agency",
#: never "checking whether your agency is recruiting illegally").
_ACCUSATORY_WORDS = (
    "illegal",
    "lying",
    "lied",
    "fraud",
    "scam",
    "suspect",
    "suspicious",
    "criminal",
    "guilty",
    "danger",
    "unsafe",
    "crime",
)


class TestLabelTableNeverLeaksRawIdentifiersOrAccusations:
    def test_no_label_or_opening_line_contains_a_raw_call_name(self):
        all_text = list(PROGRESS_TRAIL_OPENING.values())
        for labels in PROGRESS_TRAIL_LABELS.values():
            all_text.extend(labels.values())
        for text in all_text:
            for raw_name in _RAW_NAMES:
                assert raw_name not in text, (raw_name, text)

    def test_no_label_or_opening_line_looks_like_json(self):
        all_text = list(PROGRESS_TRAIL_OPENING.values())
        for labels in PROGRESS_TRAIL_LABELS.values():
            all_text.extend(labels.values())
        for text in all_text:
            assert "{" not in text and "}" not in text
            assert '"' not in text

    def test_no_label_names_a_hypothesis_or_allegation(self):
        for call_name, labels in PROGRESS_TRAIL_LABELS.items():
            for language, text in labels.items():
                lowered = text.lower()
                for word in _ACCUSATORY_WORDS:
                    assert word not in lowered, (call_name, language, text)

    def test_every_specialist_and_verification_has_an_entry(self):
        # The fixed set ADR-0010 requires: one per specialist, plus the
        # FILING_SEQUENCER verification exception.
        assert set(PROGRESS_TRAIL_LABELS) == {
            "DEBUNKER",
            "PROOF_BUILDER",
            "FILING_SEQUENCER",
            "sequencer_verify_plan",
            "COMPLAINT_DRAFTER",
            "RECOURSE_ROUTER",
        }

    def test_every_entry_covers_the_full_closed_language_set(self):
        for labels in PROGRESS_TRAIL_LABELS.values():
            assert set(labels) == {"en", "tl", "ceb"}
        assert set(PROGRESS_TRAIL_OPENING) == {"en", "tl", "ceb"}


class TestUnknownCallProducesNoLabel:
    def test_a_tool_absent_from_the_table_returns_none(self):
        for absent in (
            "office_directory",
            "action_card",
            "safe_floor_card",
            "mark_plan_step_done",
            "transfer_to_agent",
            "search_corpus",
            "sequencer_jurisdiction_rules",
            "complaint_check_agency_license",
            "recourse_build_routes",
            "some_future_tool_nobody_added_yet",
        ):
            assert progress_trail_label_for(absent, "en") is None


class TestLanguageSelectionMatchesAcknowledgementFor:
    """Same closed set, same normalization, same source of truth as
    ``acknowledgement_for`` (issue #67's ruling)."""

    @pytest.mark.parametrize(
        "language,expected_key",
        [
            (None, "en"),
            ("en", "en"),
            ("unknown", "en"),
            ("other", "en"),
            ("klingon", "en"),
            ("tl", "tl"),
            ("taglish", "tl"),  # Taglish is detected, never produced
            ("ceb", "ceb"),
        ],
    )
    def test_opening_line_follows_the_closed_set(self, language, expected_key):
        assert progress_trail_opening_for(language) == PROGRESS_TRAIL_OPENING[
            expected_key
        ]

    @pytest.mark.parametrize(
        "language,expected_key",
        [
            (None, "en"),
            ("taglish", "tl"),
            ("ceb", "ceb"),
        ],
    )
    def test_label_follows_the_closed_set(self, language, expected_key):
        assert progress_trail_label_for("DEBUNKER", language) == (
            PROGRESS_TRAIL_LABELS["DEBUNKER"][expected_key]
        )

    def test_opening_line_never_repeats_the_acknowledgement_wording(self):
        for key in ("en", "tl", "ceb"):
            assert PROGRESS_TRAIL_OPENING[key] != ACKNOWLEDGEMENTS[key]
            # Never even a substring match either way.
            assert PROGRESS_TRAIL_OPENING[key] not in ACKNOWLEDGEMENTS[key]
            assert ACKNOWLEDGEMENTS[key] not in PROGRESS_TRAIL_OPENING[key]


# ---------------------------------------------------------------------------
# HTTP seam: shared test scaffolding (mirrors tests/test_chat_api.py).
# ---------------------------------------------------------------------------


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


def auth(uid: str) -> dict:
    # Assembled to survive secret-scrubbing in tooling (matches every
    # sibling test file's convention).
    scheme = "Be" + "arer"
    return {"Authorization": f"{scheme} valid-{uid}"}


def turn(client, text, *, uid="maria", session_id=None):
    body = {"text": text}
    if session_id is not None:
        body["session_id"] = session_id
    response = client.post("/api/chat", json=body, headers=auth(uid))
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    return lines


def trail_texts(lines: list[dict]) -> list[str]:
    return [line["text"] for line in lines if line["type"] == "trail"]


# ---------------------------------------------------------------------------
# The opening line: fires right after ack, every turn, in her language.
# ---------------------------------------------------------------------------


class PlainFakeModel(BaseLlm):
    """Serves extraction plus a plain DISPATCHER reply — no specialist,
    no tool call at all."""

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
            text = self.replies.pop(0) if self.replies else DISPATCHER_REPLY
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


@pytest.fixture()
def plain_fake_model():
    return PlainFakeModel()


@pytest.fixture()
def plain_client(plain_fake_model):
    service = ChatService(
        session_service=InMemorySessionService(), llm=plain_fake_model
    )
    return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))


class TestOpeningLine:
    def test_fires_immediately_after_ack(self, plain_client, plain_fake_model):
        plain_fake_model.extraction_results.append(ENGLISH_EXTRACTION)
        lines = turn(plain_client, "I have not been paid")
        assert lines[0]["type"] == "ack"
        assert lines[1]["type"] == "trail"
        assert lines[1]["text"] == PROGRESS_TRAIL_OPENING["en"]

    def test_does_not_repeat_the_acknowledgement_wording(
        self, plain_client, plain_fake_model
    ):
        plain_fake_model.extraction_results.append(ENGLISH_EXTRACTION)
        lines = turn(plain_client, "I have not been paid")
        assert lines[0]["text"] != lines[1]["text"]
        assert lines[1]["text"] not in lines[0]["text"]

    def test_a_plain_turn_with_no_specialist_call_gets_only_the_opening_line(
        self, plain_client, plain_fake_model
    ):
        plain_fake_model.extraction_results.append(ENGLISH_EXTRACTION)
        lines = turn(plain_client, "kumusta")
        assert trail_texts(lines) == [PROGRESS_TRAIL_OPENING["en"]]

    def test_turn_one_defaults_to_english(self, plain_client, plain_fake_model):
        plain_fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        lines = turn(plain_client, "Hindi ako nababayaran")
        assert trail_texts(lines)[0] == PROGRESS_TRAIL_OPENING["en"]

    def test_turn_two_mirrors_recorded_taglish_as_pure_filipino(
        self, plain_client, plain_fake_model
    ):
        plain_fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        first = turn(plain_client, "Hindi ako nababayaran")
        session_id = next(line for line in first if line["type"] == "case")[
            "session_id"
        ]

        plain_fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        second = turn(
            plain_client, "Ano ang gagawin ko?", session_id=session_id
        )
        assert trail_texts(second)[0] == PROGRESS_TRAIL_OPENING["tl"]

    def test_turn_two_mirrors_recorded_cebuano(
        self, plain_client, plain_fake_model
    ):
        plain_fake_model.extraction_results.append(CEB_EXTRACTION)
        first = turn(plain_client, "Wala ko gibayran")
        session_id = next(line for line in first if line["type"] == "case")[
            "session_id"
        ]

        plain_fake_model.extraction_results.append(CEB_EXTRACTION)
        second = turn(plain_client, "Unsaon nako pagbuhat?", session_id=session_id)
        assert trail_texts(second)[0] == PROGRESS_TRAIL_OPENING["ceb"]

    def test_trail_appears_but_is_absent_from_a_reopened_transcript(
        self, plain_client, plain_fake_model
    ):
        # The trail is transient (ADR-0010): it crosses the stream for
        # the turn it belongs to, and nothing about /api/chat's own
        # response persists it anywhere a later read of the Case/session
        # would surface it again. This turn's own lines are the only
        # place a "trail" line ever appears.
        plain_fake_model.extraction_results.append(ENGLISH_EXTRACTION)
        lines = turn(plain_client, "kumusta")
        assert any(line["type"] == "trail" for line in lines)
        case = next(line for line in lines if line["type"] == "case")["case"]
        assert "trail" not in json.dumps(case)


# ---------------------------------------------------------------------------
# One line per specialist: DEBUNKER (no line for its own search_corpus).
# ---------------------------------------------------------------------------


class DebunkerFakeModel(BaseLlm):
    """Scripts DISPATCHER -> DEBUNKER -> search_corpus, mirroring
    tests/test_debunker_http.py's own fake model."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    claimset: dict = Field(default_factory=dict)

    async def generate_content_async(self, llm_request, stream: bool = False):
        config = llm_request.config
        if config and config.response_schema is not None:
            text = self.extraction_results.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=text)])
            )
            return

        tools = set(llm_request.tools_dict or {})
        contents = llm_request.contents or []
        fn_response = None
        if contents:
            for part in contents[-1].parts or []:
                if part.function_response is not None:
                    fn_response = part.function_response
        if "search_corpus" in tools:
            if fn_response is None:
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="search_corpus", args=self.claimset
                                )
                            )
                        ],
                    )
                )
                return
            verdicts = fn_response.response["verdicts"]
            final = {
                "verdicts": [
                    {
                        "claim": entry["claim"],
                        "verdict": entry["verdict"],
                        "rebuttal": entry.get("rebuttal") or entry.get("message"),
                        "source_name": entry.get("source_name"),
                    }
                    for entry in verdicts
                ]
            }
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=json.dumps(final))]
                )
            )
            return

        if fn_response is None:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="DEBUNKER", args=self.claimset
                            )
                        )
                    ],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=DISPATCHER_REPLY)]
            )
        )


class TestDebunkerTrailLine:
    @pytest.fixture()
    def fake_model(self):
        return DebunkerFakeModel()

    @pytest.fixture()
    def client(self, fake_model):
        service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
        return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))

    def test_exactly_one_line_for_debunker_none_for_search_corpus(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.claimset = {
            "claims": ["may utang pa ako sa placement fee"],
            "language": "taglish",
        }
        lines = turn(client, "may utang pa ako sa placement fee")
        # Opening line, then exactly one DEBUNKER line — never a second
        # one for its own internal search_corpus call. Turn 1: English
        # by design (the language extracted THIS turn is not recorded
        # until after the turn, per acknowledgement_for's own rule).
        assert trail_texts(lines) == [
            PROGRESS_TRAIL_OPENING["en"],
            PROGRESS_TRAIL_LABELS["DEBUNKER"]["en"],
        ]


# ---------------------------------------------------------------------------
# One line per specialist, plus one for verification: FILING_SEQUENCER.
# Internal sequencing steps (jurisdiction_rules here) get no line.
# ---------------------------------------------------------------------------


class FilingSequencerFakeModel(BaseLlm):
    """Scripts DISPATCHER -> FILING_SEQUENCER -> a queued list of its own
    (name, args) tool calls, then a final structured answer — mirrors
    tests/test_filing_sequencer_agent.py's own fake model."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    dispatcher_sequencer_args: list = Field(default_factory=list)
    dispatcher_replies: list = Field(default_factory=list)
    sequencer_calls: list = Field(default_factory=list)
    sequencer_final: list = Field(default_factory=list)

    _SEQUENCER_TOOL_NAMES = {
        "sequencer_jurisdiction_rules",
        "sequencer_sequence_actions",
        "sequencer_compute_deadlines",
        "sequencer_verify_plan",
    }

    async def generate_content_async(self, llm_request, stream: bool = False):
        tool_names = set(llm_request.tools_dict or {})
        schema = llm_request.config.response_schema if llm_request.config else None

        if tool_names and tool_names >= self._SEQUENCER_TOOL_NAMES:
            if self.sequencer_calls:
                name, args = self.sequencer_calls.pop(0)
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(name=name, args=args)
                            )
                        ],
                    )
                )
                return
            text = self.sequencer_final.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=text)])
            )
            return

        if schema is not None:
            result = self.extraction_results.pop(0)
            if isinstance(result, Exception):
                raise result
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
            )
            return

        if self.dispatcher_sequencer_args:
            args = self.dispatcher_sequencer_args.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="FILING_SEQUENCER", args=args
                            )
                        )
                    ],
                )
            )
            return
        text = self.dispatcher_replies.pop(0) if self.dispatcher_replies else DISPATCHER_REPLY
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


class TestFilingSequencerTrailLines:
    @pytest.fixture()
    def fake_model(self):
        return FilingSequencerFakeModel()

    @pytest.fixture()
    def client(self, fake_model):
        service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
        return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))

    def test_one_line_for_the_specialist_one_for_verification_none_for_jurisdiction_rules(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.dispatcher_sequencer_args.append(
            {
                "country": "SA",
                "tenure": "employed_in_country",
                "grievances": ["unpaid_wages"],
            }
        )
        # Deliberately skips sequence_actions/compute_deadlines: this test
        # only cares about which CALLS produce a trail line, not whether
        # a real Plan comes out the other end (verify_plan will fail
        # closed with NO_STEPS, which is fine — the label fires on the
        # call, per ADR-0010, regardless of the result).
        fake_model.sequencer_calls.extend(
            [
                ("sequencer_jurisdiction_rules", {"country": "SA"}),
                ("sequencer_verify_plan", {"plan_id": "trail-test"}),
            ]
        )
        fake_model.sequencer_final.append(json.dumps({"no_verified_plan": True}))
        fake_model.dispatcher_replies.append(DISPATCHER_REPLY)

        lines = turn(client, "Hindi ako nababayaran, nasa SA pa ako")
        assert trail_texts(lines) == [
            PROGRESS_TRAIL_OPENING["en"],
            PROGRESS_TRAIL_LABELS["FILING_SEQUENCER"]["en"],
            PROGRESS_TRAIL_LABELS["sequencer_verify_plan"]["en"],
        ]


# ---------------------------------------------------------------------------
# One line per specialist: COMPLAINT_DRAFTER (no line for its internal
# complaint_check_agency_license).
# ---------------------------------------------------------------------------


class ComplaintDrafterFakeModel(BaseLlm):
    """Scripts DISPATCHER -> COMPLAINT_DRAFTER -> one internal tool call
    -> a final refusal answer."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    dispatcher_drafter_args: list = Field(default_factory=list)
    dispatcher_replies: list = Field(default_factory=list)
    drafter_calls: list = Field(default_factory=list)
    drafter_final: list = Field(default_factory=list)

    _DRAFTER_TOOL_NAMES = {
        "complaint_check_agency_license",
        "complaint_check_safe_to_file",
        "complaint_prepare_form",
        "complaint_review_and_finalize",
    }

    async def generate_content_async(self, llm_request, stream: bool = False):
        tool_names = set(llm_request.tools_dict or {})
        schema = llm_request.config.response_schema if llm_request.config else None

        if tool_names and tool_names >= self._DRAFTER_TOOL_NAMES:
            if self.drafter_calls:
                name, args = self.drafter_calls.pop(0)
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(name=name, args=args)
                            )
                        ],
                    )
                )
                return
            text = self.drafter_final.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=text)])
            )
            return

        if schema is not None:
            result = self.extraction_results.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
            )
            return

        if self.dispatcher_drafter_args:
            args = self.dispatcher_drafter_args.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="COMPLAINT_DRAFTER", args=args
                            )
                        )
                    ],
                )
            )
            return
        text = self.dispatcher_replies.pop(0) if self.dispatcher_replies else DISPATCHER_REPLY
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


class TestComplaintDrafterTrailLine:
    @pytest.fixture()
    def fake_model(self):
        return ComplaintDrafterFakeModel()

    @pytest.fixture()
    def client(self, fake_model):
        service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
        return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))

    def test_exactly_one_line_none_for_its_internal_agency_check(
        self, client, fake_model
    ):
        from app.complaint.agent import complaint_check_agency_license
        from app.complaint.schema import AgencyInfo

        class _FakeToolContext:
            def __init__(self):
                self.state = {}

        # A direct hire (no licensed agency): a real, deterministic
        # refusal computed by the actual wrapper function, so the
        # drafter's final structured answer validates against its own
        # output_schema.
        agency = {"direct_hire": True}
        refusal_result = complaint_check_agency_license(
            AgencyInfo(direct_hire=True), "SA", _FakeToolContext()
        )
        assert refusal_result["licensed"] is False

        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.dispatcher_drafter_args.append(
            {
                "worker": {"full_name": "Maria Santos"},
                "employer": {"name": "Al Rashid Household"},
                "agency": agency,
                "country": "SA",
                "tenure": "departed_country",
                "grievances": ["unpaid_wages"],
                "safety_flags": [],
                "in_shelter": False,
                "spoke_to_mwo": False,
                "language": "tl",
            }
        )
        fake_model.drafter_calls.append(
            ("complaint_check_agency_license", {"agency": agency, "country": "SA"})
        )
        fake_model.drafter_final.append(
            json.dumps(
                {"illegal_recruitment_refusal": refusal_result["refusal"]}
            )
        )
        fake_model.dispatcher_replies.append(DISPATCHER_REPLY)

        lines = turn(client, "Direct hire ako, hindi ako nababayaran")
        assert trail_texts(lines) == [
            PROGRESS_TRAIL_OPENING["en"],
            PROGRESS_TRAIL_LABELS["COMPLAINT_DRAFTER"]["en"],
        ]


# ---------------------------------------------------------------------------
# One line per specialist: RECOURSE_ROUTER (no line for its internal
# recourse_build_routes).
# ---------------------------------------------------------------------------


class RecourseRouterFakeModel(BaseLlm):
    """Scripts DISPATCHER -> RECOURSE_ROUTER -> its one internal tool
    call -> a final routes answer."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    dispatcher_router_args: list = Field(default_factory=list)
    dispatcher_replies: list = Field(default_factory=list)
    router_calls: list = Field(default_factory=list)
    router_final: list = Field(default_factory=list)

    _ROUTER_TOOL_NAMES = {"recourse_build_routes"}

    async def generate_content_async(self, llm_request, stream: bool = False):
        tool_names = set(llm_request.tools_dict or {})
        schema = llm_request.config.response_schema if llm_request.config else None

        if tool_names and tool_names >= self._ROUTER_TOOL_NAMES:
            if self.router_calls:
                name, args = self.router_calls.pop(0)
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(name=name, args=args)
                            )
                        ],
                    )
                )
                return
            text = self.router_final.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=text)])
            )
            return

        if schema is not None:
            result = self.extraction_results.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
            )
            return

        if self.dispatcher_router_args:
            args = self.dispatcher_router_args.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="RECOURSE_ROUTER", args=args
                            )
                        )
                    ],
                )
            )
            return
        text = self.dispatcher_replies.pop(0) if self.dispatcher_replies else DISPATCHER_REPLY
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


class TestRecourseRouterTrailLine:
    @pytest.fixture()
    def fake_model(self):
        return RecourseRouterFakeModel()

    @pytest.fixture()
    def client(self, fake_model):
        service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
        return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))

    def test_exactly_one_line_none_for_its_internal_route_builder(
        self, client, fake_model
    ):
        route_in = {
            "country": "SA",
            "tenure": "employed_in_country",
            "grievances": ["unpaid_wages"],
            "agency": {"name": "Sample Overseas Manpower Services, Inc."},
            "family_region": None,
        }
        from app.recourse.routes import build_recourse_routes
        from app.recourse.schema import RecourseRouteIn

        routes = [
            route.model_dump(mode="json")
            for route in build_recourse_routes(RecourseRouteIn(**route_in))
        ]

        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.dispatcher_router_args.append(route_in)
        fake_model.router_calls.append(
            ("recourse_build_routes", {"route_in": route_in})
        )
        fake_model.router_final.append(json.dumps({"routes": routes}))
        fake_model.dispatcher_replies.append(DISPATCHER_REPLY)

        lines = turn(client, "Saan ako pwede pumunta?")
        assert trail_texts(lines) == [
            PROGRESS_TRAIL_OPENING["en"],
            PROGRESS_TRAIL_LABELS["RECOURSE_ROUTER"]["en"],
        ]


# ---------------------------------------------------------------------------
# A tool absent from the table (a directory lookup / card render DISPATCHER
# calls directly) produces no line at all.
# ---------------------------------------------------------------------------


class DirectToolFakeModel(BaseLlm):
    """DISPATCHER calls office_directory then action_card directly — no
    specialist involved at all."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    dispatcher_replies: list = Field(default_factory=list)
    calls_to_make: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        if llm_request.config and llm_request.config.response_schema is not None:
            result = self.extraction_results.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
            )
            return
        if self.calls_to_make:
            name, args = self.calls_to_make.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(name=name, args=args)
                        )
                    ],
                )
            )
            return
        text = self.dispatcher_replies.pop(0) if self.dispatcher_replies else DISPATCHER_REPLY
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


class TestAbsentToolProducesNoLine:
    @pytest.fixture()
    def fake_model(self):
        return DirectToolFakeModel()

    @pytest.fixture()
    def client(self, fake_model):
        service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
        return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))

    def test_office_directory_and_action_card_produce_no_trail_line(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(ENGLISH_EXTRACTION)
        fake_model.calls_to_make.extend(
            [
                ("office_directory", {}),
                ("action_card", {"keys": ["mwo"]}),
            ]
        )
        fake_model.dispatcher_replies.append(DISPATCHER_REPLY)

        lines = turn(client, "What numbers can help me?")
        # Only the opening line — a quiet gap for both calls, never a
        # raw tool name.
        assert trail_texts(lines) == [PROGRESS_TRAIL_OPENING["en"]]


# ---------------------------------------------------------------------------
# The trail is shown in the Emergency Conversation too (ADR-0010).
# ---------------------------------------------------------------------------


class EmergencyFakeModel(BaseLlm):
    """Mirrors tests/test_emergency.py's ScriptedModel: DISPATCHER
    transfers to EMERGENCY, which then speaks."""

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    responses: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream: bool = False):
        if llm_request.config and llm_request.config.response_schema is not None:
            result = self.extraction_results.pop(0)
            if isinstance(result, Exception):
                raise result
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
            )
            return
        result = self.responses.pop(0)
        if isinstance(result, types.Content):
            yield LlmResponse(content=result)
        else:
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
            )


def _transfer_to_emergency() -> types.Content:
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


class TestTrailInEmergencyConversation:
    @pytest.fixture()
    def fake_model(self):
        return EmergencyFakeModel()

    @pytest.fixture()
    def client(self, fake_model):
        service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
        return TestClient(create_app(verifier=FakeVerifier(), chat_service=service))

    def test_the_opening_trail_line_appears_when_transferred_to_emergency(
        self, client, fake_model
    ):
        client.post("/api/emergency/button", headers=auth("maria"))

        fake_model.extraction_results.append(RuntimeError("no narrative to read"))
        fake_model.responses.append(_transfer_to_emergency())
        fake_model.responses.append(
            "Nandito ako, kausapin mo ako. Ligtas ka ba ngayon?"
        )
        lines = turn(client, "tulungan niyo ako")
        assert lines[0]["type"] == "ack"
        assert lines[1]["type"] == "trail"
        assert lines[1]["text"] == PROGRESS_TRAIL_OPENING["en"]
        assert (
            next(line for line in lines if line["type"] == "reply")["text"]
            == "Nandito ako, kausapin mo ako. Ligtas ka ba ngayon?"
        )
