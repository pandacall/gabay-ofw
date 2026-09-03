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


class TestSequenceActionsRefusesCaseCountryMismatch:
    """Issue #43, ADR-0006: a code-owned defense-in-depth check —
    staleness detection can mark a plan inactive because her Case's
    country changed, but that guarantee is only real if DISPATCHER is
    also refused from republishing a plan built on a country that no
    longer matches her Case, whatever args it happens to supply.
    """

    def test_supplied_country_disagreeing_with_case_is_refused(self):
        ctx = _FakeToolContext()
        ctx.state["case"] = {
            "claims": {
                "country": {
                    "value": "Qatar",
                    "source": "user",
                    "confidence": "high",
                    "at": "T1",
                    "user_confirmed": True,
                    "conflicts": [],
                }
            }
        }
        # DISPATCHER (stale or mistaken) still supplies SA.
        result = sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        assert result == {
            "ok": False,
            "reason": "CASE_COUNTRY_MISMATCH",
            "detail": (
                "supplied country 'SA' disagrees with the Case's own "
                "resolved country 'QA'"
            ),
        }
        assert "temp:filing_sequencer_seq_in" not in ctx.state

    def test_agreeing_country_proceeds(self):
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

    def test_no_case_country_yet_never_blocks(self):
        # UNKNOWN/PH (no resolvable jurisdiction) — no signal to compare,
        # so a first-ever call with no Case country on file proceeds.
        ctx = _FakeToolContext()
        ctx.state["case"] = {"claims": {}}
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

    def test_persists_the_published_plan_and_its_seq_in_across_turns(self):
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        result = sequencer_verify_plan("plan-1", ctx)
        assert result["ok"] is True
        assert ctx.state["plan"]["plan_id"] == "plan-1"
        assert ctx.state["plan_seq_in"]["country"] == "SA"
        assert ctx.state["plan_active"] is True

    def test_a_brand_new_plan_never_carries_a_delta_or_was_stale(self):
        # A delta/was_stale is only meaningful relative to a PRIOR plan —
        # the very first plan ever built for a session is not a
        # regeneration, even though reconcile_plan(None, plan) internally
        # reports every step as "added".
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        result = sequencer_verify_plan("plan-1", ctx)
        assert result["ok"] is True
        assert "delta" not in result
        assert "was_stale" not in result


class TestVerifyPlanToolStaleness:
    """Issue #43, ADR-0006: regeneration against a persisted prior plan."""

    def test_regeneration_carries_done_steps_and_surfaces_delta(self):
        from app.sequencer import Plan
        from app.staleness import mark_step_done

        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        first = sequencer_verify_plan("plan-1", ctx)
        assert first["ok"] is True
        done_step_id = first["plan"]["steps"][0]["id"]

        # She reports having already filed the wages step.
        plan = Plan.model_validate(ctx.state["plan"])
        ctx.state["plan"] = mark_step_done(plan, done_step_id).model_dump(
            mode="json"
        )

        # A new turn: she now also reports her passport withheld — a
        # genuine SequencerIn change (input-hash mismatch) that adds a
        # step while the original wages row (same id) still applies.
        sequencer_sequence_actions(
            "SA",
            "employed_in_country",
            ["unpaid_wages", "passport_withheld"],
            ctx,
        )
        sequencer_compute_deadlines(ctx)
        second = sequencer_verify_plan("plan-1", ctx)

        assert second["ok"] is True
        assert second["was_stale"] is True
        by_id = {step["id"]: step for step in second["plan"]["steps"]}
        assert by_id[done_step_id]["status"] == "DONE"
        assert done_step_id in second["delta"]["carried_done"]
        assert len(second["delta"]["added"]) == 1
        assert second["plan"]["version"] == 2

    def test_same_input_republish_is_not_stale_and_has_no_delta(self):
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        first = sequencer_verify_plan("plan-1", ctx)
        assert first["ok"] is True

        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        second = sequencer_verify_plan("plan-1", ctx)
        assert second["ok"] is True
        assert "was_stale" not in second
        assert "delta" not in second

    def test_regeneration_that_fails_verify_ships_no_sequence(self):
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        first = sequencer_verify_plan("plan-1", ctx)
        assert first["ok"] is True
        assert ctx.state["plan"] is not None

        # A new turn with a changed SequencerIn (stale trigger), but the
        # steps that would build the replacement are tampered so the
        # regenerated plan itself fails verify_plan.
        sequencer_sequence_actions(
            "SA", "departed_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        bad_steps = ctx.state["temp:filing_sequencer_steps"]
        bad_steps[0]["rule_citation"]["url"] = "not-a-url"
        ctx.state["temp:filing_sequencer_steps"] = bad_steps

        result = sequencer_verify_plan("plan-1", ctx)
        assert result["ok"] is False
        assert result["reason"] == "VERIFY_FAILED"
        assert result["regeneration_failed"] is True
        # Ship NO sequence: neither the stale original nor the unverified
        # replacement is ever left standing (ADR-0006).
        assert ctx.state["plan"] is None
        assert ctx.state["plan_active"] is False

    def test_a_verify_failure_that_was_never_stale_leaves_the_persisted_plan_untouched(
        self,
    ):
        # A verify failure on a rebuild attempt that was NOT triggered by
        # an input-hash mismatch must not be treated as "regeneration
        # failed" — there is a perfectly good, still-current plan
        # persisted, and this failed call must not invalidate it.
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        first = sequencer_verify_plan("plan-1", ctx)
        assert first["ok"] is True

        # Same SequencerIn (not stale) — tamper the steps directly so
        # this rebuild attempt fails verify_plan for an unrelated reason.
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        bad_steps = ctx.state["temp:filing_sequencer_steps"]
        bad_steps[0]["rule_citation"]["url"] = "not-a-url"
        ctx.state["temp:filing_sequencer_steps"] = bad_steps

        result = sequencer_verify_plan("plan-1", ctx)
        assert result["ok"] is False
        assert result["regeneration_failed"] is False
        # The persisted (still valid, still non-stale) plan stands.
        assert ctx.state["plan"] is not None
        assert ctx.state["plan"]["plan_id"] == "plan-1"
        assert ctx.state["plan_active"] is True


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


TAGLISH_EXTRACTION_QA_CORRECTION = json.dumps(
    {
        "language": "taglish",
        "claims": {
            "country": {"value": "Qatar", "confidence": "high"},
        },
        "safety_flags": [],
    }
)


class TestPlanStalenessHttpSeam:
    """Issue #43, ADR-0006, HTTP seam: a case correction that changes a
    SequencerIn field flips the rendered plan to inactive with the
    explanation line — driven entirely by code (the root before-agent
    callback's staleness recheck plus ``ChatService``'s unconditional
    render), with zero reliance on DISPATCHER calling any tool that turn.
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

    def _publish_sa_plan(self, client, fake_model):
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
        fake_model.sequencer_final.append(json.dumps({"plan": verified["plan"]}))
        fake_model.dispatcher_replies.append("Narito ang verified na plano mo.")

        lines = turn(client, "Hindi ako nababayaran, kasalukuyan pa akong SA")
        by_type = {line["type"]: line for line in lines}
        assert by_type["card"]["card"]["type"] == "plan"
        return by_type["reply"]["session_id"]

    def test_country_correction_deactivates_the_plan_without_a_tool_call(
        self, client, fake_model
    ):
        session_id = self._publish_sa_plan(client, fake_model)

        # Turn 2: she corrects her country. DISPATCHER is scripted to just
        # reply — it never calls FILING_SEQUENCER or safe_floor_card this
        # turn — yet the plan must still render inactive with the Safe
        # Floor and its explanation line, driven purely by code.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION_QA_CORRECTION)
        fake_model.dispatcher_replies.append(
            "Ay, Qatar pala ang kasalukuyan mong bansa — ituturo ko na sa"
            " tamang opisina."
        )

        lines = turn(
            client, "Pasensya, Qatar na pala ako ngayon", session_id=session_id
        )
        by_type = {line["type"]: line for line in lines}
        assert "card" in by_type, "the deactivated plan must render a card"
        card = by_type["card"]["card"]
        assert card["type"] == "safe_floor"
        assert card["reason"] == "FACTS_CHANGED"
        assert "nagbago" in card["reason_line"] or "changed" in card["reason_line"]
        # Never the stale plan presented as current.
        assert by_type["card"]["card"].get("steps") is None

    def test_tenure_correction_across_a_rule_boundary_regenerates_with_a_delta(
        self, client, fake_model
    ):
        # Demoable (issue #43): correcting tenure across a rule boundary
        # (still-employed -> left-the-employer) visibly deactivates the
        # old plan and the regenerated one shows what changed.
        session_id = self._publish_sa_plan(client, fake_model)

        # Precompute exactly what the real sequencer_verify_plan call will
        # produce this turn, replaying the same session-state sequence
        # turn 1 left behind before regenerating against it.
        ctx = _FakeToolContext()
        sequencer_sequence_actions(
            "SA", "employed_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        sequencer_verify_plan("demo-plan", ctx)

        sequencer_sequence_actions(
            "SA", "left_employer_in_country", ["unpaid_wages"], ctx
        )
        sequencer_compute_deadlines(ctx)
        regenerated = sequencer_verify_plan("demo-plan", ctx)
        assert regenerated["ok"] is True
        assert regenerated["was_stale"] is True
        assert len(regenerated["delta"]["added"]) == 1
        assert len(regenerated["delta"]["removed"]) == 1

        fake_model.extraction_results.append(
            json.dumps({"language": "taglish", "claims": {}, "safety_flags": []})
        )
        fake_model.dispatcher_sequencer_args.append(
            {
                "country": "SA",
                "tenure": "left_employer_in_country",
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
                        "tenure": "left_employer_in_country",
                        "grievances": ["unpaid_wages"],
                    },
                ),
                ("sequencer_compute_deadlines", {}),
                ("sequencer_verify_plan", {"plan_id": "demo-plan"}),
            ]
        )
        fake_model.sequencer_final.append(
            json.dumps({k: v for k, v in regenerated.items() if k != "ok"})
        )
        fake_model.dispatcher_replies.append(
            "Nabago ang plano mo dahil umalis ka na sa amo — ito ang bagong hakbang."
        )

        lines = turn(
            client,
            "Umalis na ako sa amo ko, SA pa rin ako",
            session_id=session_id,
        )
        by_type = {line["type"]: line for line in lines}
        card = by_type["card"]["card"]
        assert card["type"] == "plan"
        assert card["was_stale"] is True
        assert len(card["delta"]["added"]) == 1
        assert len(card["delta"]["removed"]) == 1

    def test_failed_regeneration_ships_an_action_card_deterministically(
        self, client, fake_model
    ):
        # ADR-0006: "If regeneration runs and verify_plan does not
        # clear: ship no sequence — Safe Floor plus action card." The
        # Safe Floor half of that guarantee is proven by the country-
        # correction test above (driven by the persisted plan_active
        # flag); this test isolates the OTHER half — the action card —
        # proving it renders from the "regeneration_failed" flag alone,
        # even though DISPATCHER's own scripted reply never calls
        # action_card itself. The guarantee is code-owned
        # (ChatService.stream_turn), not model compliance.
        session_id = self._publish_sa_plan(client, fake_model)

        fake_model.extraction_results.append(
            json.dumps({"language": "taglish", "claims": {}, "safety_flags": []})
        )
        fake_model.dispatcher_sequencer_args.append(
            {
                "country": "SA",
                "tenure": "left_employer_in_country",
                "grievances": ["unpaid_wages"],
            }
        )
        # No sequencer_calls scripted: FILING_SEQUENCER's single model
        # turn goes straight to its final answer below, bypassing the
        # real internal tool calls entirely — this isolates chat.py's
        # OWN handling of the structured answer from whatever the real
        # pure-function pipeline would separately do.
        # FILING_SEQUENCER's final answer when its own regeneration
        # attempt failed verify_plan: no plan, just the refusal shape.
        fake_model.sequencer_final.append(
            json.dumps({"no_verified_plan": True, "regeneration_failed": True})
        )
        fake_model.dispatcher_replies.append(
            "Kailangan nating i-verify muna ulit ito bago ko masabi sa'yo."
        )

        lines = turn(
            client,
            "Umalis na ako sa amo ko, SA pa rin ako",
            session_id=session_id,
        )
        card_lines = [line for line in lines if line["type"] == "card"]
        card_types = {card["card"]["type"] for card in card_lines}
        assert "action_card" in card_types
        # Never the stale original nor an unverified replacement.
        assert "plan" not in card_types
        # Never the stale original nor an unverified replacement.
        assert "plan" not in card_types

