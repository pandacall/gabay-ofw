"""FILING_SEQUENCER agent-wiring tests (issue #42): tool-wrapper unit tests
plus the HTTP-seam demoable path (PRD #34's testing decision).

No API key: the tool wrapper tests call the plain Python wrapper functions
in ``app.sequencer_agent`` directly (bypassing the model entirely), and the
HTTP-seam tests use the existing ``FakeModelRunner`` pattern from
``tests/test_chat_api.py`` to drive one full DISPATCHER turn that triggers
FILING_SEQUENCER, asserting on the resulting NDJSON lines only.
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
from app.sequencer_agent import (
    FilingSequencerOut,
    build_filing_sequencer,
    sequencer_compute_deadlines,
    sequencer_jurisdiction_rules,
    sequencer_sequence_actions,
    sequencer_verify_plan,
)


class _FakeState(dict):
    pass


class _FakeToolContext:
    """A minimal stand-in exposing only ``.state`` (dict-like), the only
    ToolContext surface these wrappers touch."""

    def __init__(self):
        self.state = _FakeState()


# ---------------------------------------------------------------------------
# Tool wrapper unit tests — no model, no HTTP.
# ---------------------------------------------------------------------------


class TestSequencerJurisdictionRulesTool:
    def test_active_country(self):
        ctx = _FakeToolContext()
        result = sequencer_jurisdiction_rules("SA", ctx)
        assert result == {"country": "SA", "status": "active"}

    def test_held_country_includes_refusal_card(self):
        ctx = _FakeToolContext()
        result = sequencer_jurisdiction_rules("KW", ctx)
        assert result["country"] == "KW"
        assert result["status"] == "held"
        assert result["card"]["type"] == "held_refusal"


class TestSequenceActionsToolRefusals:
    def test_held_jurisdiction_returns_refusal_card_not_rows(self):
        ctx = _FakeToolContext()
        result = sequencer_sequence_actions(
            "KW", "employed_in_country", ["unpaid_wages"], ctx
        )
        assert result["ok"] is False
        assert result["reason"] == "JURISDICTION_HELD"
        assert "MWO" in result["card"]["message"]
        assert result["card"]["country"] == "KW"

    def test_ae_jurisdiction_also_refuses(self):
        ctx = _FakeToolContext()
        result = sequencer_sequence_actions(
            "AE", "departed_country", ["exit_blocked"], ctx
        )
        assert result["ok"] is False
        assert result["reason"] == "JURISDICTION_HELD"

    def test_active_jurisdiction_returns_steps_and_stashes_state(self):
        ctx = _FakeToolContext()
        result = sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        assert result["ok"] is True
        assert len(result["steps"]) == 1
        assert result["steps"][0]["rule_citation"]["source_name"]
        assert "temp:filing_sequencer_seq_in" in ctx.state
        assert "temp:filing_sequencer_rows" in ctx.state


class TestSequenceActionsBlocksOnUnresolvedConflict:
    """Issue #44: an unresolved Conflict on a SequencerIn-mapped Case
    field (country, tenure, grievances) blocks invocation before any rows
    are built — code-owned, not left to DISPATCHER's judgment. A Conflict
    on any other field is informational and never blocks.
    """

    def test_unresolved_country_conflict_blocks_before_sequencing(self):
        ctx = _FakeToolContext()
        ctx.state["case"] = {
            "claims": {
                "country": {
                    "value": "Saudi Arabia",
                    "source": "extraction",
                    "confidence": "high",
                    "at": "T1",
                    "conflicts": [
                        {
                            "value": "Kuwait",
                            "source": "document",
                            "confidence": "high",
                            "at": "T2",
                        }
                    ],
                }
            }
        }
        result = sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        assert result == {
            "ok": False,
            "reason": "UNRESOLVED_CONFLICT",
            "field": "country",
        }
        # Never proceeds to build rows or stash sequencer state.
        assert "temp:filing_sequencer_seq_in" not in ctx.state
        assert "temp:filing_sequencer_rows" not in ctx.state

    def test_non_sequencer_field_conflict_never_blocks(self):
        ctx = _FakeToolContext()
        ctx.state["case"] = {
            "claims": {
                "employer_name": {
                    "value": "Al Rashid",
                    "source": "extraction",
                    "confidence": "high",
                    "at": "T1",
                    "conflicts": [
                        {
                            "value": "Al Fahad",
                            "source": "document",
                            "confidence": "high",
                            "at": "T2",
                        }
                    ],
                }
            }
        }
        result = sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        assert result["ok"] is True

    def test_resolved_conflict_no_longer_blocks(self):
        ctx = _FakeToolContext()
        ctx.state["case"] = {
            "claims": {
                "country": {
                    "value": "Saudi Arabia",
                    "source": "user",
                    "confidence": "high",
                    "at": "T1",
                    "user_confirmed": True,
                    "conflicts": [],
                }
            }
        }
        result = sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        assert result["ok"] is True


class TestComputeDeadlinesToolRequiresPriorState:
    def test_without_prior_sequence_actions_call_refuses(self):
        ctx = _FakeToolContext()
        result = sequencer_compute_deadlines(ctx)
        assert result == {
            "ok": False,
            "reason": "NO_ROWS",
            "detail": "call sequence_actions first",
        }

    def test_after_sequence_actions_attaches_deadlines(self):
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        result = sequencer_compute_deadlines(ctx)
        assert result["ok"] is True
        assert len(result["steps"]) == 1
        # ReportedDeadline (Tier-2) never becomes a countdown (ADR-0005).
        assert result["steps"][0]["expires_at"] is None
        assert "temp:filing_sequencer_steps" in ctx.state


class TestVerifyPlanToolPublishesOnSuccess:
    def test_full_pipeline_yields_a_published_plan(self):
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        result = sequencer_verify_plan("plan-1", ctx)
        assert result["ok"] is True
        plan = result["plan"]
        assert plan["plan_id"] == "plan-1"
        assert plan["steps"][0]["rule_citation"]["source_name"]

    def test_without_prior_steps_refuses(self):
        ctx = _FakeToolContext()
        result = sequencer_verify_plan("plan-1", ctx)
        assert result["ok"] is False
        assert result["reason"] == "NO_STEPS"


class TestBuildFilingSequencer:
    def test_single_turn_with_closed_enum_input_schema(self):
        from app.sequencer import SequencerIn

        class _NeverCalled(BaseLlm):
            model: str = "structural-test-only"

            async def generate_content_async(self, llm_request, stream=False):
                raise AssertionError("must never call the model")
                yield LlmResponse(content=types.Content(role="model", parts=[]))

        fs = build_filing_sequencer(_NeverCalled())
        assert fs.name == "FILING_SEQUENCER"
        assert fs.mode == "single_turn"
        assert fs.input_schema is SequencerIn
        assert fs.output_schema is FilingSequencerOut
        tool_names = {getattr(t, "name", getattr(t, "__name__", None)) for t in fs.tools}
        assert tool_names == {
            "sequencer_jurisdiction_rules",
            "sequencer_sequence_actions",
            "sequencer_compute_deadlines",
            "sequencer_verify_plan",
        }


# ---------------------------------------------------------------------------
# HTTP-seam demo tests (PRD #34): SA unpaid-wages -> verified cited Plan;
# KW -> the fixed refusal. Pattern matches tests/test_chat_api.py.
# ---------------------------------------------------------------------------

TAGLISH_EXTRACTION_SA = json.dumps(
    {
        "language": "taglish",
        "claims": {
            "country": {"value": "Saudi Arabia", "confidence": "high"},
            "months_unpaid": {"value": "3", "confidence": "high"},
        },
        "safety_flags": [],
    }
)

TAGLISH_EXTRACTION_KW = json.dumps(
    {
        "language": "taglish",
        "claims": {
            "country": {"value": "Kuwait", "confidence": "high"},
            "months_unpaid": {"value": "2", "confidence": "high"},
        },
        "safety_flags": [],
    }
)


class FakeModelRunnerWithFilingSequencer(BaseLlm):
    """Serves extraction, DISPATCHER, and FILING_SEQUENCER turns.

    Distinguishes the three call sites by ``llm_request.tools_dict``: the
    FILING_SEQUENCER node is the only one whose available tools are the
    four sequencer wrapper functions. Extraction is the only one with a
    ``response_schema`` and no tools. Within FILING_SEQUENCER's own turn,
    a scripted queue of function-call names drives its four tools in
    order, then a final ``FilingSequencerOut``-shaped JSON answer.
    """

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    dispatcher_replies: list = Field(default_factory=list)
    dispatcher_sequencer_args: list = Field(default_factory=list)
    sequencer_calls: list = Field(default_factory=list)
    sequencer_final: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

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
            # A FILING_SEQUENCER turn: either the next scripted tool call,
            # or (once the script is empty) the final structured answer.
            if self.sequencer_calls:
                self.calls.append("filing_sequencer_tool_call")
                name, args = self.sequencer_calls.pop(0)
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name=name, args=args
                                )
                            )
                        ],
                    )
                )
                return
            self.calls.append("filing_sequencer_final")
            text = self.sequencer_final.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=text)]
                )
            )
            return

        if schema is not None:
            self.calls.append("extraction")
            result = self.extraction_results.pop(0)
            if isinstance(result, Exception):
                raise result
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=result)]
                )
            )
            return

        # A DISPATCHER turn: call FILING_SEQUENCER (its auto-wrapped tool)
        # first if scripted, then the final reply text.
        if self.dispatcher_sequencer_args:
            self.calls.append("dispatcher_calls_filing_sequencer")
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
        self.calls.append("dispatcher")
        text = self.dispatcher_replies.pop(0) if self.dispatcher_replies else "OK"
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
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
    if session_id is not None:
        body["session_id"] = session_id
    response = client.post("/api/chat", json=body, headers=auth(uid))
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    return lines


class TestFilingSequencerHttpSeam:
    """The demoable HTTP path (PRD #34, tests/test_api.py pattern): a full
    /api/chat turn that drives FILING_SEQUENCER through scripted tool
    calls on the fake model, asserting on the resulting NDJSON lines only
    — no internals mocked below the model boundary.
    """

    @pytest.fixture()
    def fake_model(self):
        return FakeModelRunnerWithFilingSequencer()

    @pytest.fixture()
    def client(self, fake_model):
        service = ChatService(
            session_service=InMemorySessionService(), llm=fake_model
        )
        app = create_app(verifier=FakeVerifier(), chat_service=service)
        return TestClient(app)

    def test_sa_unpaid_wages_yields_a_verified_cited_plan_card(
        self, client, fake_model
    ):
        # Build the exact plan JSON FILING_SEQUENCER's final answer must
        # match, using the same wrapper functions it calls internally.
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        verified = sequencer_verify_plan("demo-plan", ctx)
        assert verified["ok"] is True

        fake_model.extraction_results.append(TAGLISH_EXTRACTION_SA)
        fake_model.dispatcher_sequencer_args.append(
            {
                "country": "SA",
                "tenure": "employed_in_country",
                "grievances": ["unpaid_wages"],
            }
        )
        fake_model.sequencer_calls.extend(
            [
                ("sequencer_jurisdiction_rules", {"country": "SA"}),
                (
                    "sequencer_sequence_actions",
                    {
                        "country": "SA",
                        "tenure": "employed_in_country",
                        "grievances": ["unpaid_wages"],
                    },
                ),
                ("sequencer_compute_deadlines", {}),
                ("sequencer_verify_plan", {"plan_id": "demo-plan"}),
            ]
        )
        fake_model.sequencer_final.append(
            json.dumps({"plan": verified["plan"]})
        )
        fake_model.dispatcher_replies.append("Narito ang verified na plano mo.")

        lines = turn(client, "Hindi ako nababayaran, kasalukuyan pa akong SA")
        by_type = {line["type"]: line for line in lines}
        assert "card" in by_type
        card = by_type["card"]["card"]
        assert card["type"] == "plan"
        assert card["steps"], "the rendered card must carry the verified steps"
        for step in card["steps"]:
            assert step["rule_citation"]["source_name"]
        assert by_type["reply"]["text"] == "Narito ang verified na plano mo."

    def test_kw_yields_the_fixed_refusal_card(self, client, fake_model):
        ctx = _FakeToolContext()
        result = sequencer_jurisdiction_rules("KW", ctx)
        assert result["status"] == "held"

        fake_model.extraction_results.append(TAGLISH_EXTRACTION_KW)
        fake_model.dispatcher_sequencer_args.append(
            {
                "country": "KW",
                "tenure": "employed_in_country",
                "grievances": ["unpaid_wages"],
            }
        )
        fake_model.sequencer_calls.append(
            ("sequencer_jurisdiction_rules", {"country": "KW"})
        )
        fake_model.sequencer_final.append(
            json.dumps({"held_refusal": result["card"]})
        )
        fake_model.dispatcher_replies.append(
            "Wala pa tayong verified filing order para diyan, kausapin ang MWO."
        )

        lines = turn(client, "Nasa Kuwait ako, hindi ako nababayaran")
        by_type = {line["type"]: line for line in lines}
        card = by_type["card"]["card"]
        assert card["type"] == "held_refusal"
        assert card["country"] == "KW"
        assert "1348" in json.dumps(card)
