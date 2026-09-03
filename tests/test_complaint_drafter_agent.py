"""COMPLAINT_DRAFTER agent-wiring tests (issue #46): tool-wrapper unit
tests plus the HTTP-seam demoable path (PRD #34's testing decision).

No API key: the tool wrapper tests call the plain Python wrapper
functions in ``app.complaint.agent`` directly (bypassing the model
entirely), and the HTTP-seam tests use the existing ``FakeModelRunner``
pattern from ``tests/test_filing_sequencer_agent.py`` /
``tests/test_chat_api.py`` to drive one full DISPATCHER turn that
triggers COMPLAINT_DRAFTER, asserting on the resulting NDJSON lines only.
"""

from __future__ import annotations

import base64
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
from app.complaint.agent import (
    COMPLAINT_DRAFTER_NAME,
    build_complaint_drafter,
    complaint_check_agency_license,
    complaint_check_safe_to_file,
    complaint_prepare_form,
    complaint_review_and_finalize,
)
from app.complaint.schema import (
    AgencyInfo,
    ComplaintDraftIn,
    ComplaintDraftOut,
    EmployerInfo,
    WageLossInput,
    WorkerInfo,
)
from app.guard import ALLOWED_TOOLS, guard_before_tool
from app.main import create_app


class _FakeState(dict):
    pass


class _FakeToolContext:
    """A minimal stand-in exposing only ``.state`` (dict-like), the only
    ToolContext surface these wrappers touch."""

    def __init__(self):
        self.state = _FakeState()


WORKER = WorkerInfo(full_name="Maria Santos", sex="female")
EMPLOYER = EmployerInfo(name="Al Rashid Household", address="Riyadh")
LICENSED_AGENCY = AgencyInfo(name="Sample Overseas Manpower Services, Inc.")
WAGE_LOSS = WageLossInput(
    monthly_salary="1500.00",
    currency="SAR",
    months_unpaid=3,
    period_start="2026-01-01",
    period_end="2026-04-01",
)
CHRONOLOGY = (
    "Maria Santos worked as a domestic worker for the Al Rashid household "
    "in Riyadh from 2024-01-01 to 2026-06-01."
)
PARTIES = (
    "Requesting party: Maria Santos. Responding party: Al Rashid Household "
    "(employer)."
)
AMOUNTS = "She was not paid for the last three months of her contract."
REMEDIES = (
    "She is requesting payment of her unpaid wages through the DOLE "
    "Single-Entry Approach."
)


# ---------------------------------------------------------------------------
# Tool wrapper unit tests — no model, no HTTP.
# ---------------------------------------------------------------------------


class TestCheckAgencyLicenseTool:
    def test_licensed_agency_clears(self):
        ctx = _FakeToolContext()
        result = complaint_check_agency_license(
            AgencyInfo(name="Sample Overseas Manpower Services, Inc."),
            "SA",
            ctx,
        )
        assert result["licensed"] is True
        assert result["refusal"] is None
        assert ctx.state["temp:complaint_agency_licensed"] is True

    def test_unlicensed_agency_refuses(self):
        ctx = _FakeToolContext()
        result = complaint_check_agency_license(
            AgencyInfo(name="Placeholder Global Recruitment Corp."),
            "SA",
            ctx,
        )
        assert result["licensed"] is False
        assert result["refusal"]["reason"] == "UNLICENSED_AGENCY"
        assert "illegal recruitment" in result["refusal"]["message"].lower()

    def test_direct_hire_refuses(self):
        ctx = _FakeToolContext()
        result = complaint_check_agency_license(
            AgencyInfo(direct_hire=True), "QA", ctx
        )
        assert result["licensed"] is False
        assert result["refusal"]["reason"] == "DIRECT_HIRE"


class TestCheckSafeToFileTool:
    def test_departed_and_acute_is_safe(self):
        ctx = _FakeToolContext()
        result = complaint_check_safe_to_file(
            "departed_country", ["physical_abuse_or_danger"], [], "SA", ctx
        )
        assert result["safe_to_file"] is True

    def test_not_departed_and_acute_refuses(self):
        ctx = _FakeToolContext()
        result = complaint_check_safe_to_file(
            "employed_in_country", ["physical_abuse_or_danger"], [], "SA", ctx
        )
        assert result["safe_to_file"] is False
        assert "safely out" in result["refusal"]["message"]

    def test_not_departed_but_no_acute_grievance_is_safe(self):
        ctx = _FakeToolContext()
        result = complaint_check_safe_to_file(
            "employed_in_country", ["unpaid_wages"], [], "SA", ctx
        )
        assert result["safe_to_file"] is True


class TestPrepareFormToolRequiresPriorGates:
    def test_without_agency_gate_refuses(self):
        ctx = _FakeToolContext()
        result = complaint_prepare_form(
            WORKER, EMPLOYER, AgencyInfo(), ["unpaid_wages"], ctx
        )
        assert result["ok"] is False
        assert result["reason"] == "AGENCY_NOT_CLEARED"

    def test_after_both_gates_fills_form(self):
        ctx = _FakeToolContext()
        complaint_check_agency_license(LICENSED_AGENCY, "SA", ctx)
        complaint_check_safe_to_file(
            "departed_country", ["unpaid_wages"], [], "SA", ctx
        )
        result = complaint_prepare_form(
            WORKER, EMPLOYER, LICENSED_AGENCY, ["unpaid_wages"], ctx, WAGE_LOSS
        )
        assert result["ok"] is True
        assert result["sena_rfa"]["requesting_party_name"] == "Maria Santos"
        assert result["arabic_loss_calculation"]["total_amount"] == "4500.00"


class TestReviewAndFinalizeTool:
    def _prepared_ctx(self) -> _FakeToolContext:
        ctx = _FakeToolContext()
        complaint_check_agency_license(LICENSED_AGENCY, "SA", ctx)
        complaint_check_safe_to_file(
            "departed_country", ["unpaid_wages"], [], "SA", ctx
        )
        complaint_prepare_form(
            WORKER, EMPLOYER, LICENSED_AGENCY, ["unpaid_wages"], ctx, WAGE_LOSS
        )
        return ctx

    def test_without_prepared_form_refuses(self):
        ctx = _FakeToolContext()
        result = complaint_review_and_finalize(
            CHRONOLOGY, PARTIES, AMOUNTS, REMEDIES,
            "departed_country", ["unpaid_wages"], ctx,
        )
        assert result["ok"] is False
        assert result["reason"] == "NO_FORM"

    def test_clean_narrative_finalizes_a_draft(self):
        ctx = self._prepared_ctx()
        result = complaint_review_and_finalize(
            CHRONOLOGY, PARTIES, AMOUNTS, REMEDIES,
            "departed_country", ["unpaid_wages"], ctx,
        )
        assert result["ok"] is True
        draft = result["draft"]
        assert draft["red_team"]["cleared"] is True
        assert draft["intake_narrative_en"]["chronology"] == CHRONOLOGY
        assert draft["intake_narrative_en"]["remedies"] == REMEDIES
        pdf_bytes = base64.b64decode(draft["sena_rfa_pdf_base64"])
        assert pdf_bytes.startswith(b"%PDF")

    def test_leaking_narrative_returns_findings_for_revision(self):
        ctx = self._prepared_ctx()
        leaking_remedies = REMEDIES + " She is currently staying in a shelter."
        result = complaint_review_and_finalize(
            CHRONOLOGY, PARTIES, AMOUNTS, leaking_remedies,
            "departed_country", ["unpaid_wages"], ctx,
        )
        assert result["ok"] is False
        assert result["reason"] == "RED_TEAM_FINDINGS"
        assert result["findings"]

    def test_premature_identification_returns_a_refusal_not_findings(self):
        ctx = _FakeToolContext()
        complaint_check_agency_license(LICENSED_AGENCY, "SA", ctx)
        # Deliberately skip complaint_check_safe_to_file to simulate a
        # defense-in-depth scenario where the structural finding still
        # fires inside the finalize gate.
        ctx.state["temp:complaint_safe_to_file"] = True
        complaint_prepare_form(
            WORKER,
            EMPLOYER,
            LICENSED_AGENCY,
            ["physical_abuse_or_danger", "unpaid_wages"],
            ctx,
        )
        result = complaint_review_and_finalize(
            CHRONOLOGY, PARTIES, AMOUNTS, REMEDIES,
            "employed_in_country",
            ["physical_abuse_or_danger", "unpaid_wages"],
            ctx,
        )
        assert result["ok"] is False
        assert result["reason"] == "PREMATURE_FILING"
        assert "refusal" in result


class TestBuildComplaintDrafter:
    def test_single_turn_with_closed_enum_schemas(self):
        class _NeverCalled(BaseLlm):
            model: str = "structural-test-only"

            async def generate_content_async(self, llm_request, stream=False):
                raise AssertionError("must never call the model")
                yield LlmResponse(content=types.Content(role="model", parts=[]))

        agent = build_complaint_drafter(_NeverCalled())
        assert agent.name == COMPLAINT_DRAFTER_NAME
        assert agent.mode == "single_turn"
        assert agent.input_schema is ComplaintDraftIn
        assert agent.output_schema is ComplaintDraftOut
        assert agent.before_tool_callback is guard_before_tool
        assert agent.disallow_transfer_to_parent
        assert agent.disallow_transfer_to_peers
        tool_names = {
            getattr(t, "name", getattr(t, "__name__", None)) for t in agent.tools
        }
        assert tool_names == {
            "complaint_check_agency_license",
            "complaint_check_safe_to_file",
            "complaint_prepare_form",
            "complaint_review_and_finalize",
        }

    def test_all_tool_names_are_allowlisted_by_routing_guard(self):
        assert COMPLAINT_DRAFTER_NAME in ALLOWED_TOOLS
        for name in (
            "complaint_check_agency_license",
            "complaint_check_safe_to_file",
            "complaint_prepare_form",
            "complaint_review_and_finalize",
        ):
            assert name in ALLOWED_TOOLS


# ---------------------------------------------------------------------------
# HTTP-seam demo tests (PRD #34): SA licensed-agency wage claim -> a
# rendered, red-team-cleared FormDraft; an unlicensed agency -> the
# illegal-recruitment refusal; an unsafe moment -> the premature-filing
# refusal.
# ---------------------------------------------------------------------------

TAGLISH_EXTRACTION = json.dumps(
    {
        "language": "taglish",
        "claims": {"country": {"value": "Saudi Arabia", "confidence": "high"}},
        "safety_flags": [],
    }
)


class FakeModelRunnerWithComplaintDrafter(BaseLlm):
    """Serves extraction, DISPATCHER, and COMPLAINT_DRAFTER turns.

    Distinguishes the three call sites by ``llm_request.tools_dict``: the
    COMPLAINT_DRAFTER node is the only one whose available tools are its
    four wrapper functions. Extraction is the only one with a
    ``response_schema`` and no tools. Within COMPLAINT_DRAFTER's own
    turn, a scripted queue of function-call names drives its tools in
    order, then a final ``ComplaintDraftOut``-shaped JSON answer.
    """

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    dispatcher_replies: list = Field(default_factory=list)
    dispatcher_drafter_args: list = Field(default_factory=list)
    drafter_calls: list = Field(default_factory=list)
    drafter_final: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)
    requests: list = Field(default_factory=list)

    _DRAFTER_TOOL_NAMES = {
        "complaint_check_agency_license",
        "complaint_check_safe_to_file",
        "complaint_prepare_form",
        "complaint_review_and_finalize",
    }

    async def generate_content_async(self, llm_request, stream: bool = False):
        tool_names = set(llm_request.tools_dict or {})
        self.requests.append((tool_names, llm_request))
        schema = llm_request.config.response_schema if llm_request.config else None

        if tool_names and tool_names >= self._DRAFTER_TOOL_NAMES:
            if self.drafter_calls:
                self.calls.append("complaint_drafter_tool_call")
                name, args = self.drafter_calls.pop(0)
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
            self.calls.append("complaint_drafter_final")
            text = self.drafter_final.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=text)]
                )
            )
            return

        if schema is not None:
            self.calls.append("extraction")
            result = self.extraction_results.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=result)]
                )
            )
            return

        if self.dispatcher_drafter_args:
            self.calls.append("dispatcher_calls_complaint_drafter")
            args = self.dispatcher_drafter_args.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=COMPLAINT_DRAFTER_NAME, args=args
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
    scheme = "Be" + "arer"
    return {"Authorization": f"{scheme} valid-{uid}"}


def turn(client, text, *, uid="maria"):
    response = client.post("/api/chat", json={"text": text}, headers=auth(uid))
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    return lines


def complaint_drafter_request_texts(fake_model) -> list[str]:
    """All text COMPLAINT_DRAFTER's own model turn actually saw (its
    typed ComplaintDraftIn JSON) — mirrors PROOF_BUILDER's isolation
    check in tests/test_proof_builder_api.py."""
    texts = []
    for tool_names, request in fake_model.requests:
        if not (tool_names and tool_names >= fake_model._DRAFTER_TOOL_NAMES):
            continue
        for content in request.contents or []:
            for part in content.parts or []:
                if part.text:
                    texts.append(part.text)
    return texts


_DRAFTER_ARGS = {
    "worker": {"full_name": "Maria Santos", "sex": "female"},
    "employer": {"name": "Al Rashid Household", "address": "Riyadh"},
    "agency": {"name": "Sample Overseas Manpower Services, Inc."},
    "country": "SA",
    "tenure": "departed_country",
    "grievances": ["unpaid_wages"],
    "wage_loss": {
        "monthly_salary": "1500.00",
        "currency": "SAR",
        "months_unpaid": 3,
        "period_start": "2026-01-01",
        "period_end": "2026-04-01",
    },
    "safety_flags": [],
    "in_shelter": False,
    "spoke_to_mwo": False,
    "language": "en",
}

_PLAN_FIXTURE = {
    "plan_id": "demo-plan-fixture",
    "version": 1,
    "input_hash": "abc123",
    "steps": [
        {
            "id": "sa-wages-1",
            "status": "PENDING",
            "rule_citation": {
                "source_name": "Test Source",
                "reference": "Test reference",
                "url": "https://example.test",
                "tier": "tier_1",
            },
            "expires_at": None,
            "grievance": "unpaid_wages",
            "file_where": "MWO Riyadh",
            "action_class": "protective_reversible",
            "tier": "tier_1",
            "confirm_first_notes": [],
            "warnings": [],
            "notes": [],
        }
    ],
}


class TestComplaintDrafterHttpSeam:
    @pytest.fixture()
    def fake_model(self):
        return FakeModelRunnerWithComplaintDrafter()

    @pytest.fixture()
    def client(self, fake_model):
        service = ChatService(
            session_service=InMemorySessionService(), llm=fake_model
        )
        app = create_app(verifier=FakeVerifier(), chat_service=service)
        return TestClient(app)

    def test_licensed_agency_yields_a_red_team_cleared_draft(
        self, client, fake_model
    ):
        # Compute the exact expected result using the same wrapper
        # functions COMPLAINT_DRAFTER calls internally.
        ctx = _FakeToolContext()
        agency_result = complaint_check_agency_license(
            AgencyInfo(name="Sample Overseas Manpower Services, Inc."),
            "SA",
            ctx,
        )
        assert agency_result["licensed"] is True
        safe_result = complaint_check_safe_to_file(
            "departed_country", ["unpaid_wages"], [], "SA", ctx
        )
        assert safe_result["safe_to_file"] is True
        prepare_result = complaint_prepare_form(
            WORKER, EMPLOYER, AgencyInfo(name="Sample Overseas Manpower Services, Inc."),
            ["unpaid_wages"], ctx, WAGE_LOSS,
        )
        assert prepare_result["ok"] is True
        finalize_result = complaint_review_and_finalize(
            CHRONOLOGY, PARTIES, AMOUNTS, REMEDIES,
            "departed_country", ["unpaid_wages"], ctx,
        )
        assert finalize_result["ok"] is True

        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.dispatcher_drafter_args.append(_DRAFTER_ARGS)
        fake_model.drafter_calls.extend(
            [
                (
                    "complaint_check_agency_license",
                    {
                        "agency": _DRAFTER_ARGS["agency"],
                        "country": "SA",
                    },
                ),
                (
                    "complaint_check_safe_to_file",
                    {
                        "tenure": "departed_country",
                        "grievances": ["unpaid_wages"],
                        "safety_flags": [],
                        "country": "SA",
                    },
                ),
                (
                    "complaint_prepare_form",
                    {
                        "worker": _DRAFTER_ARGS["worker"],
                        "employer": _DRAFTER_ARGS["employer"],
                        "agency": _DRAFTER_ARGS["agency"],
                        "grievances": ["unpaid_wages"],
                        "wage_loss": _DRAFTER_ARGS["wage_loss"],
                    },
                ),
                (
                    "complaint_review_and_finalize",
                    {
                        "chronology": CHRONOLOGY,
                        "parties": PARTIES,
                        "amounts": AMOUNTS,
                        "remedies": REMEDIES,
                        "tenure": "departed_country",
                        "grievances": ["unpaid_wages"],
                        "safety_flags": [],
                    },
                ),
            ]
        )
        fake_model.drafter_final.append(
            json.dumps({"draft": finalize_result["draft"]})
        )
        fake_model.dispatcher_replies.append(
            "Handa na ang SEnA form mo — pakisuri bago i-file."
        )

        lines = turn(client, "Gusto ko nang mag-file ng SEnA complaint.")
        by_type = {line["type"]: line for line in lines}
        assert "complaint_draft" in by_type
        draft = by_type["complaint_draft"]["complaint_draft"]["draft"]
        assert draft["red_team"]["cleared"] is True
        pdf_bytes = base64.b64decode(draft["sena_rfa_pdf_base64"])
        assert pdf_bytes.startswith(b"%PDF")
        assert by_type["reply"]["text"] == (
            "Handa na ang SEnA form mo — pakisuri bago i-file."
        )

    def test_unlicensed_agency_yields_illegal_recruitment_refusal(
        self, client, fake_model
    ):
        ctx = _FakeToolContext()
        unlicensed_agency = {"name": "Placeholder Global Recruitment Corp."}
        agency_result = complaint_check_agency_license(
            AgencyInfo(name="Placeholder Global Recruitment Corp."), "SA", ctx
        )
        assert agency_result["licensed"] is False

        args = dict(_DRAFTER_ARGS, agency=unlicensed_agency)
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.dispatcher_drafter_args.append(args)
        fake_model.drafter_calls.append(
            (
                "complaint_check_agency_license",
                {"agency": unlicensed_agency, "country": "SA"},
            )
        )
        fake_model.drafter_final.append(
            json.dumps(
                {"illegal_recruitment_refusal": agency_result["refusal"]}
            )
        )
        fake_model.dispatcher_replies.append(
            "Mali ang venue para diyan — hindi licensed ang agency mo."
        )

        lines = turn(client, "Gusto ko mag-file, ito ang agency ko.")
        by_type = {line["type"]: line for line in lines}
        card = by_type["complaint_draft"]["complaint_draft"]
        assert card["illegal_recruitment_refusal"]["reason"] == "UNLICENSED_AGENCY"
        assert card.get("draft") is None

    def test_unsafe_moment_yields_premature_filing_refusal(
        self, client, fake_model
    ):
        ctx = _FakeToolContext()
        agency_result = complaint_check_agency_license(
            AgencyInfo(name="Sample Overseas Manpower Services, Inc."), "SA", ctx
        )
        assert agency_result["licensed"] is True
        safe_result = complaint_check_safe_to_file(
            "employed_in_country", ["physical_abuse_or_danger"], [], "SA", ctx
        )
        assert safe_result["safe_to_file"] is False

        args = dict(
            _DRAFTER_ARGS,
            tenure="employed_in_country",
            grievances=["physical_abuse_or_danger"],
            wage_loss=None,
        )
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.dispatcher_drafter_args.append(args)
        fake_model.drafter_calls.extend(
            [
                (
                    "complaint_check_agency_license",
                    {"agency": _DRAFTER_ARGS["agency"], "country": "SA"},
                ),
                (
                    "complaint_check_safe_to_file",
                    {
                        "tenure": "employed_in_country",
                        "grievances": ["physical_abuse_or_danger"],
                        "safety_flags": [],
                        "country": "SA",
                    },
                ),
            ]
        )
        fake_model.drafter_final.append(
            json.dumps(
                {"premature_filing_refusal": safe_result["refusal"]}
            )
        )
        fake_model.dispatcher_replies.append(
            "Huwag muna mag-file — lumabas ka muna nang ligtas at kausapin ang MWO."
        )

        lines = turn(client, "May physical danger ako pero nasa amo pa ako.")
        by_type = {line["type"]: line for line in lines}
        card = by_type["complaint_draft"]["complaint_draft"]
        assert card["premature_filing_refusal"] is not None
        assert card.get("draft") is None
        assert "safely out" in card["premature_filing_refusal"]["message"]

    def test_the_model_sees_plan_and_shelter_mwo_flags_in_its_own_input(
        self, client, fake_model
    ):
        # ComplaintDraftIn's `plan`, `in_shelter`, and `spoke_to_mwo`
        # fields are not re-supplied to any tool call (the tools only
        # need worker/employer/agency/grievances/wage_loss) — they are
        # carried in the sub-agent's own initial turn content instead,
        # the same mechanism PROOF_BUILDER's BundleState uses. This
        # asserts they are actually present there, not dead input.
        args = dict(
            _DRAFTER_ARGS,
            agency={"name": "Placeholder Global Recruitment Corp."},
            plan=_PLAN_FIXTURE,
            in_shelter=True,
            spoke_to_mwo=True,
        )
        ctx = _FakeToolContext()
        agency_result = complaint_check_agency_license(
            AgencyInfo(name="Placeholder Global Recruitment Corp."), "SA", ctx
        )
        assert agency_result["licensed"] is False

        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.dispatcher_drafter_args.append(args)
        fake_model.drafter_calls.append(
            (
                "complaint_check_agency_license",
                {"agency": args["agency"], "country": "SA"},
            )
        )
        fake_model.drafter_final.append(
            json.dumps(
                {"illegal_recruitment_refusal": agency_result["refusal"]}
            )
        )
        fake_model.dispatcher_replies.append("Mali ang venue para diyan.")

        turn(client, "Gusto ko mag-file, ito ang agency ko.")

        texts = complaint_drafter_request_texts(fake_model)
        assert texts, "COMPLAINT_DRAFTER never ran"
        first_turn_json = json.loads(texts[0])
        assert first_turn_json["plan"]["plan_id"] == "demo-plan-fixture"
        assert first_turn_json["in_shelter"] is True
        assert first_turn_json["spoke_to_mwo"] is True
