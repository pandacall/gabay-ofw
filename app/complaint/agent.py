"""COMPLAINT_DRAFTER as an agent: wiring the pure cores into DISPATCHER
(issue #46, PRD #34).

COMPLAINT_DRAFTER is a ``mode='single_turn'`` :class:`LlmAgent` attached to
DISPATCHER via ``sub_agents=[...]``, auto-wrapped by google-adk==2.8.0 into
a single tool named after the sub-agent — same integration pattern as
FILING_SEQUENCER (issue #42), DEBUNKER (issue #47), and PROOF_BUILDER
(issue #45): typed ``input_schema``/``output_schema``, its own
``before_tool_callback=guard_before_tool`` (the second, independent
ROUTING_GUARD rail), and transfers disallowed both ways.

Pipeline, in the order the instruction has the model call these tools:

1. ``complaint_check_agency_license`` — the correctness gate (issue #46):
   an unlicensed agency or a direct hire means SEnA is the wrong
   instrument. Stops here with :class:`IllegalRecruitmentRefusal` when
   the agency does not clear.
2. ``complaint_check_safe_to_file`` — the second structural gate: an
   acute grievance/safety flag while she has not yet departed makes
   naming her in a filing itself the risk ("naming her before she is
   out"). Stops here with :class:`PrematureFilingRefusal` when unsafe.
3. ``complaint_prepare_form`` — deterministically fills the SEnA RFA
   fields and computes the Arabic arithmetic-only loss calculation.
4. The model drafts the English MWO/ATN intake narrative itself (no
   tool call — free text reasoning), instructed to never state that she
   is leaving, in a shelter, her exact location, or that she has already
   contacted the MWO.
5. ``complaint_review_and_finalize`` — draft -> red-team -> revise: runs
   the fixed leak-check list (``safety_review``) against the drafted
   narrative. A revisable text finding returns violations for the model
   to address and call again; only a red-team-CLEARED narrative is
   rendered to PDF and assembled into the published :class:`FormDraft`
   — this wrapper is the output gate, the same discipline
   ``sequencer_verify_plan`` uses for FILING_SEQUENCER's Plan.

Fills, never submits: no tool in this module, or anywhere under
:mod:`app.complaint`, performs network I/O or names a submission
endpoint.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.tools import ToolContext

from app.complaint.agency import check_agency_license, is_wrong_venue
from app.complaint.loss_calc import compute_wage_loss
from app.complaint.pdf import render_pdf_base64
from app.complaint.redteam import ACUTE_GRIEVANCES, safety_review
from app.complaint.schema import (
    AgencyInfo,
    AgencyLicenseStatus,
    ComplaintDraftIn,
    ComplaintDraftOut,
    EmployerInfo,
    FormDraft,
    IllegalRecruitmentRefusal,
    PrematureFilingRefusal,
    RedTeamCheckId,
    REFUSAL_MESSAGES,
    WageLossInput,
    WorkerInfo,
)
from app.complaint.sena_form import NoSenaClaimError, fill_sena_rfa
from app.directory import Country, office_directory_rows
from app.guard import guard_before_tool
from app.rules.schema import Grievance, TenureBucket

logger = logging.getLogger(__name__)

COMPLAINT_DRAFTER_NAME = "COMPLAINT_DRAFTER"

_AGENCY_STATUS_TO_REASON: dict[AgencyLicenseStatus, str] = {
    AgencyLicenseStatus.DIRECT_HIRE: "DIRECT_HIRE",
    AgencyLicenseStatus.NOT_FOUND: "AGENCY_STATUS_UNVERIFIED",
    AgencyLicenseStatus.DELISTED: "UNLICENSED_AGENCY",
    AgencyLicenseStatus.CANCELLED: "UNLICENSED_AGENCY",
    AgencyLicenseStatus.EXPIRED: "UNLICENSED_AGENCY",
}


def _routing_for(country: str) -> dict[str, Any]:
    """MWO/OWWA/DMW routing rows for the refusal cards, resolved
    server-side (never model-supplied) and dialability-filtered — same
    discipline as DEBUNKER's ``mwo_routing`` (app/debunker.py)."""
    return {"rows": office_directory_rows(Country(country))}


# ---------------------------------------------------------------------------
# 1. complaint_check_agency_license
# ---------------------------------------------------------------------------


def complaint_check_agency_license(
    agency: AgencyInfo,
    country: Literal["SA", "QA", "KW", "AE"],
    tool_context: ToolContext,
) -> dict[str, Any]:
    """The correctness gate (issue #46): an unlicensed agency or a direct
    hire means SEnA is the wrong instrument. Call this FIRST, before any
    other tool. Stores whether the agency cleared in this turn's state so
    ``complaint_prepare_form`` refuses to run without it (defense in
    depth against a future caller skipping this gate)."""
    result = check_agency_license(agency.name, direct_hire=agency.direct_hire)
    licensed = not is_wrong_venue(result)
    tool_context.state["temp:complaint_agency_licensed"] = licensed
    tool_context.state["temp:complaint_country"] = country
    if licensed:
        return {"licensed": True, "status": result.status.value, "refusal": None}

    reason = _AGENCY_STATUS_TO_REASON[result.status]
    refusal = IllegalRecruitmentRefusal(
        reason=reason,
        agency_status=result.status,
        message=REFUSAL_MESSAGES[reason],
        routing=_routing_for(country),
    )
    return {
        "licensed": False,
        "status": result.status.value,
        "refusal": refusal.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# 2. complaint_check_safe_to_file
# ---------------------------------------------------------------------------


def complaint_check_safe_to_file(
    tenure: Literal[
        "employed_in_country", "left_employer_in_country", "departed_country"
    ],
    grievances: list[
        Literal[
            "unpaid_wages",
            "passport_withheld",
            "physical_abuse_or_danger",
            "status_retaliation",
            "exit_blocked",
        ]
    ],
    safety_flags: list[str],
    country: Literal["SA", "QA", "KW", "AE"],
    tool_context: ToolContext,
) -> dict[str, Any]:
    """The second structural gate: refuses a named filing while she has
    an acute grievance/safety flag and has not yet departed the country.
    No rewording clears this later — only her situation changing does,
    so it is checked here, before any drafting happens, not inside the
    red-team revise loop."""
    tenure_value = TenureBucket(tenure)
    grievance_values = [Grievance(g) for g in grievances]
    acute = bool(safety_flags) or any(
        g in ACUTE_GRIEVANCES for g in grievance_values
    )
    unsafe = acute and tenure_value is not TenureBucket.DEPARTED_COUNTRY
    tool_context.state["temp:complaint_safe_to_file"] = not unsafe
    if not unsafe:
        return {"safe_to_file": True, "refusal": None}
    refusal = PrematureFilingRefusal(routing=_routing_for(country))
    return {"safe_to_file": False, "refusal": refusal.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# 3. complaint_prepare_form
# ---------------------------------------------------------------------------


def complaint_prepare_form(
    worker: WorkerInfo,
    employer: EmployerInfo,
    agency: AgencyInfo,
    grievances: list[
        Literal[
            "unpaid_wages",
            "passport_withheld",
            "physical_abuse_or_danger",
            "status_retaliation",
            "exit_blocked",
        ]
    ],
    tool_context: ToolContext,
    wage_loss: Optional[WageLossInput] = None,
) -> dict[str, Any]:
    """Deterministically fills the SEnA RFA and computes the Arabic
    arithmetic-only loss calculation. Refuses to run unless both prior
    gates cleared this turn (defense in depth: a caller cannot skip
    straight to filling a form for an unlicensed agency or an unsafe
    moment)."""
    if not tool_context.state.get("temp:complaint_agency_licensed"):
        return {"ok": False, "reason": "AGENCY_NOT_CLEARED"}
    if not tool_context.state.get("temp:complaint_safe_to_file"):
        return {"ok": False, "reason": "NOT_SAFE_TO_FILE"}

    grievance_values = tuple(Grievance(g) for g in grievances)
    try:
        sena_rfa = fill_sena_rfa(
            worker=worker,
            employer=employer,
            agency=agency,
            grievances=grievance_values,
            has_wage_loss=wage_loss is not None,
        )
    except NoSenaClaimError as exc:
        return {"ok": False, "reason": "NO_SENA_CLAIM", "detail": str(exc)}

    loss_calc = compute_wage_loss(wage_loss) if wage_loss is not None else None

    tool_context.state["temp:complaint_sena_rfa"] = sena_rfa.model_dump(
        mode="json"
    )
    tool_context.state["temp:complaint_loss_calc"] = (
        loss_calc.model_dump(mode="json") if loss_calc is not None else None
    )
    return {
        "ok": True,
        "sena_rfa": sena_rfa.model_dump(mode="json"),
        "arabic_loss_calculation": (
            loss_calc.model_dump(mode="json") if loss_calc is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# 5. complaint_review_and_finalize — draft -> red-team -> revise's gate.
# ---------------------------------------------------------------------------


def complaint_review_and_finalize(
    narrative_en: str,
    tenure: Literal[
        "employed_in_country", "left_employer_in_country", "departed_country"
    ],
    grievances: list[
        Literal[
            "unpaid_wages",
            "passport_withheld",
            "physical_abuse_or_danger",
            "status_retaliation",
            "exit_blocked",
        ]
    ],
    tool_context: ToolContext,
    safety_flags: list[str] | None = None,
) -> dict[str, Any]:
    """Runs ``safety_review`` against ``narrative_en``. A revisable text
    finding returns violations for the model to address and call again;
    a ``PREMATURE_IDENTIFICATION`` finding — which no rewording can clear
    — stops the loop and returns the fixed refusal instead. Only a
    CLEARED review renders the PDF and assembles the published
    :class:`FormDraft`."""
    raw_sena_rfa = tool_context.state.get("temp:complaint_sena_rfa")
    if not raw_sena_rfa:
        return {
            "ok": False,
            "reason": "NO_FORM",
            "detail": "call complaint_prepare_form first",
        }

    from app.complaint.schema import SenaRfaFields  # local import, avoid cycle noise

    sena_rfa = SenaRfaFields.model_validate(raw_sena_rfa)
    raw_loss_calc = tool_context.state.get("temp:complaint_loss_calc")

    revision_count = int(
        tool_context.state.get("temp:complaint_revision_count") or 0
    )
    result = safety_review(
        narrative_en,
        tenure=TenureBucket(tenure),
        grievances=tuple(Grievance(g) for g in grievances),
        safety_flags=tuple(safety_flags or ()),
    )
    if not result.cleared:
        revision_count += 1
        tool_context.state["temp:complaint_revision_count"] = revision_count
        result = result.model_copy(update={"revision_count": revision_count})
        if any(
            f.check_id is RedTeamCheckId.PREMATURE_IDENTIFICATION
            for f in result.findings
        ):
            country_value = tool_context.state.get("temp:complaint_country")
            refusal = PrematureFilingRefusal(
                routing=(
                    _routing_for(country_value)
                    if country_value
                    else {"rows": []}
                )
            )
            return {
                "ok": False,
                "reason": "PREMATURE_FILING",
                "refusal": refusal.model_dump(mode="json"),
            }
        return {
            "ok": False,
            "reason": "RED_TEAM_FINDINGS",
            "findings": [f.model_dump(mode="json") for f in result.findings],
        }

    result = result.model_copy(update={"revision_count": revision_count})
    pdf_base64 = render_pdf_base64(sena_rfa)
    draft = FormDraft(
        sena_rfa=sena_rfa,
        sena_rfa_pdf_base64=pdf_base64,
        intake_narrative_en=narrative_en,
        arabic_loss_calculation=raw_loss_calc,
        red_team=result,
    )
    return {"ok": True, "draft": draft.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# The agent.
# ---------------------------------------------------------------------------

_INSTRUCTION = """\
You are COMPLAINT_DRAFTER. You never talk to the worker directly — your
input is typed arguments only: her worker/employer/agency identity, her
country, tenure, grievances, an optional wage-loss figure, and any safety
flags on her Case. Fills, NEVER submits — there is no tool here that
files anything anywhere; every tool only drafts.

Call your tools in this exact order:

1. complaint_check_agency_license(agency, country) — if licensed is
   false, STOP: respond with exactly
   {"illegal_recruitment_refusal": <the returned refusal, unchanged>}.
   Never call another tool after this refusal.
2. complaint_check_safe_to_file(tenure, grievances, safety_flags,
   country) — if safe_to_file is false, STOP: respond with exactly
   {"premature_filing_refusal": <the returned refusal, unchanged>}.
   Never call another tool after this refusal.
3. complaint_prepare_form(worker, employer, agency, grievances,
   wage_loss) — fills the SEnA RFA fields and computes the Arabic
   arithmetic-only loss calculation (if a wage_loss was given). If ok is
   false, do not fabricate a form — stop and report the failure reason.
4. Draft the structured MWO/ATN intake narrative YOURSELF, in English:
   chronology, parties (worker/employer/agency), amounts, and remedies,
   drawn only from the typed facts you were given and the Plan (if one
   was given). NEVER state that she is leaving her employer, that she is
   in a shelter, her exact current location, or that she has already
   contacted the MWO — even though you may know these things, the
   recruitment agency receives this filing and is the party most likely
   still in contact with her employer.
5. complaint_review_and_finalize(narrative_en, tenure, grievances,
   safety_flags) — if ok is false with reason RED_TEAM_FINDINGS, REWRITE
   the narrative addressing every finding's guidance exactly (never just
   delete a sentence and resubmit unchanged) and call this tool again. If
   ok is false with reason PREMATURE_FILING, STOP: respond with exactly
   {"premature_filing_refusal": <the returned refusal, unchanged>} — no
   rewording fixes this one. When ok is true, respond with exactly
   {"draft": <the returned draft, unchanged>}.

Never fabricate a citation, a form field, or a loss amount — everything
in your final response must come from a tool result, copied verbatim.
"""


def build_complaint_drafter(llm: BaseLlm) -> LlmAgent:
    """Builds COMPLAINT_DRAFTER: ``mode='single_turn'``, closed-enum
    ``input_schema``, its five pure-function-backed tools, and a
    structured ``output_schema``. Attach via ``sub_agents=[...]`` on
    DISPATCHER — google-adk auto-wraps this as ONE tool named
    ``COMPLAINT_DRAFTER``."""
    return LlmAgent(
        name=COMPLAINT_DRAFTER_NAME,
        mode="single_turn",
        model=llm,
        description=(
            "Fills the SEnA Request for Assistance and the MWO/ATN "
            "intake narrative from her Case and Plan, red-teams its own "
            "draft, and computes an arithmetic-only Arabic wage-loss "
            "calculation. Refuses an unlicensed agency, a direct hire, "
            "or naming her before she is safely out. Fills, never "
            "submits."
        ),
        instruction=_INSTRUCTION,
        input_schema=ComplaintDraftIn,
        output_schema=ComplaintDraftOut,
        tools=[
            complaint_check_agency_license,
            complaint_check_safe_to_file,
            complaint_prepare_form,
            complaint_review_and_finalize,
        ],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        before_tool_callback=guard_before_tool,
    )
