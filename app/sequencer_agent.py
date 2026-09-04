"""FILING_SEQUENCER as an agent: wiring the pure core into DISPATCHER
(issue #42, ADR-0006, PRD #34).

FILING_SEQUENCER is a ``mode='single_turn'`` :class:`LlmAgent` attached to
DISPATCHER via ``sub_agents=[...]``. google-adk==2.8.0 auto-wraps a
``single_turn`` sub-agent as a single tool named after the sub-agent
itself (``LlmAgent.model_post_init``, ``tools/agent_tool.py``'s
``_SingleTurnAgentTool``) — DISPATCHER never imports ``AgentTool``
directly and never sees the four pure functions below as its own tools.

The output gate (ADR-0006) is enforced in code, not trusted to the model:
``verify_plan`` is exposed as one of FILING_SEQUENCER's four tools exactly
as the PRD lists it, but its wrapper here *also* calls ``publish_plan``
against the exact ``Plan`` object it just verified and returns the
published (or refused) result. The model can see verification happen and
narrate it, but it cannot claim a plan is published without this wrapper
having actually cleared it — there is no separate model-callable
``publish_plan`` step to skip. A plan hash ``verify_plan`` has not
cleared can never reach ``publish_plan``'s allow path (it is
recomputed from the plan's own content, so a plan built from
mismatching/edited steps also refuses, per ``publish_plan``'s docstring
in ``app/sequencer.py``).

If violations remain (either flagged by ``verify_plan`` or by
``sequence_actions``/``compute_deadlines`` raising), no sequence is
returned — Safe Floor plus an action card, never a partially-cited plan
under a verified-looking UI (ADR-0006: an uncited deadline shipping under
the same UI as a verified one is worse than nothing).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.tools import ToolContext
from pydantic import BaseModel

from app.case import unresolved_sequencer_conflict
from app.directory import resolve_case_country
from app.plan_ops import republish
from app.rules import Grievance, Jurisdiction, JurisdictionStatus, TenureBucket
from app.sequencer import (
    JurisdictionHeldError,
    NoVerifiedPlanError,
    Plan,
    SequencerIn,
    compute_deadlines,
    held_refusal_card,
    jurisdiction_rules,
    sequence_actions,
)
from app.state_keys import CASE, PLAN, PLAN_ACTIVE, PLAN_MUTATIONS, PLAN_SEQ_IN

logger = logging.getLogger(__name__)

FILING_SEQUENCER_NAME = "FILING_SEQUENCER"

# ---------------------------------------------------------------------------
# FILING_SEQUENCER's four LLM-callable tools (PRD #42: "chooses across four
# PURE-FUNCTION tools"). Each is a thin ToolContext-taking wrapper: the pure
# functions in app/sequencer.py stay untouched, model-args are converted
# through Pydantic/enum validation (never trusted raw), and every raised
# refusal (HELD jurisdiction, no verified plan, failed/tampered
# verification) becomes a structured no-sequence result, never an
# invented step.
# ---------------------------------------------------------------------------


def sequencer_jurisdiction_rules(
    country: Literal["SA", "QA", "KW", "AE"],
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Whether ``country``'s filing sequence is ACTIVE (verified rows
    exist) or HELD (no verified sequence — refuse, do not guess).

    Call this first, before ``sequence_actions``, so a HELD jurisdiction
    is recognized before any sequencing is attempted. When HELD, includes
    the fixed refusal ``card`` (MWO directory + 1348) so the caller never
    needs to invent one.
    """
    jurisdiction = Jurisdiction(country)
    status = jurisdiction_rules(jurisdiction)
    result: dict[str, Any] = {"country": jurisdiction.value, "status": status.value}
    if status is JurisdictionStatus.HELD:
        result["card"] = held_refusal_card(jurisdiction)
    return result


def sequencer_sequence_actions(
    country: Literal["SA", "QA", "KW", "AE"],
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
) -> dict[str, Any]:
    """The ordered, cited filing-action rows for one worker situation.

    RAISES no exception to the model: a HELD jurisdiction (KW, AE) or a
    situation with no sourced rule row returns a ``held`` /
    ``no_verified_plan`` refusal result instead of rows — never an
    invented sequence. Refuses first, code-owned, when the Case carries
    an unresolved Conflict on a SequencerIn-mapped field (``country`` or
    ``tenure_months`` — see ``app.case.SEQUENCER_FIELDS``): a wrong
    jurisdiction or a disputed tenure duration would build a
    verified-looking Plan around a fact she hasn't confirmed (issue #44)
    — DISPATCHER never even reaches ``sequence_actions`` in that state.
    Also refuses, code-owned, when the supplied ``country`` disagrees
    with her Case's own resolved country (issue #43): staleness
    detection can mark a plan inactive because her country changed, but
    that guarantee is only real if DISPATCHER is also refused from
    republishing a plan built on the OLD country it might still be
    holding onto — this check is what makes that refusal happen in code
    rather than depending on the model noticing and re-deriving country
    itself. On success, stores the built ``SequencerIn`` and its rows in
    session state (``temp:``, this turn only) so ``compute_deadlines``
    and ``verify_plan`` can be called without the model re-transmitting
    the full row payload.
    """
    case = tool_context.state.get(CASE)
    blocked_field = unresolved_sequencer_conflict(case)
    if blocked_field:
        return {
            "ok": False,
            "reason": "UNRESOLVED_CONFLICT",
            "field": blocked_field,
        }

    case_country = resolve_case_country(case)
    try:
        case_jurisdiction: Optional[Jurisdiction] = Jurisdiction(case_country.value)
    except ValueError:
        case_jurisdiction = None  # UNKNOWN/PH: no known-jurisdiction signal to check.
    if case_jurisdiction is not None and case_jurisdiction.value != country:
        return {
            "ok": False,
            "reason": "CASE_COUNTRY_MISMATCH",
            "detail": (
                f"supplied country {country!r} disagrees with the Case's "
                f"own resolved country {case_jurisdiction.value!r}"
            ),
        }

    try:
        seq_in = SequencerIn(
            country=Jurisdiction(country),
            tenure=TenureBucket(tenure),
            grievances=tuple(Grievance(g) for g in grievances),
        )
    except ValueError as exc:
        return {"ok": False, "reason": "INVALID_INPUT", "detail": str(exc)}

    try:
        rows = sequence_actions(seq_in)
    except JurisdictionHeldError:
        card = held_refusal_card(seq_in.country)
        return {"ok": False, "reason": "JURISDICTION_HELD", "card": card}
    except NoVerifiedPlanError as exc:
        return {"ok": False, "reason": "NO_VERIFIED_PLAN", "detail": str(exc)}

    tool_context.state["temp:filing_sequencer_seq_in"] = seq_in.model_dump(
        mode="json"
    )
    tool_context.state["temp:filing_sequencer_rows"] = [
        row.model_dump(mode="json") for row in rows
    ]
    return {
        "ok": True,
        "steps": [
            {
                "id": row.row_id,
                "grievance": row.grievance.value,
                "file_where": row.file_where,
                "rule_citation": row.citation.model_dump(mode="json"),
            }
            for row in rows
        ],
    }


def sequencer_compute_deadlines(tool_context: ToolContext) -> dict[str, Any]:
    """Attaches each step's ``expires_at`` from the rows ``sequence_actions``
    just built (read from this turn's session state, never re-supplied by
    the model). Only a Tier-1 ``HardDeadline`` becomes a countdown; a
    Tier-2 ``ReportedDeadline`` never does (ADR-0005) — it rides in
    ``notes`` instead, so a Saudi exit-visa timing note renders
    confirm-first, never as a countdown.
    """
    from app.rules import RuleRow

    raw_rows = tool_context.state.get("temp:filing_sequencer_rows")
    if not raw_rows:
        return {
            "ok": False,
            "reason": "NO_ROWS",
            "detail": "call sequence_actions first",
        }
    rows = tuple(RuleRow.model_validate(row) for row in raw_rows)
    steps = compute_deadlines(rows, now=datetime.now(timezone.utc))
    tool_context.state["temp:filing_sequencer_steps"] = [
        step.model_dump(mode="json") for step in steps
    ]
    return {
        "ok": True,
        "steps": [
            {
                "id": step.id,
                "grievance": step.grievance.value,
                "expires_at": step.expires_at,
                "tier": step.tier.value,
                "notes": list(step.notes),
                "confirm_first_notes": list(step.confirm_first_notes),
            }
            for step in steps
        ],
    }


def sequencer_verify_plan(
    plan_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Builds, verifies, AND publishes the Plan from this turn's computed
    steps — the output gate (ADR-0006).

    ``verify_plan`` itself is pure and only checks; this wrapper is what
    actually gates: a plan that fails ``verify_plan`` is never published,
    and even a plan that passes is republished through ``publish_plan``
    against its own recomputed hash, so nothing reaches the caller except
    a hash ``verify_plan`` has just cleared for this exact content. If
    violations remain, no sequence is returned — the caller must fall
    back to Safe Floor, never render a partially-cited plan.

    Staleness (issue #43, ADR-0006) is handled here too, against the
    session's PERSISTED prior plan (``state[PLAN]``, never the
    ``temp:`` scratch this turn's rows live in): ``is_input_stale`` is
    the pure check of whether this turn's ``SequencerIn`` still hashes to
    the persisted plan's ``input_hash``; regardless of the answer,
    ``reconcile_plan`` carries any DONE step forward onto the freshly
    built plan by step id (never a silent renumber) and surfaces the
    delta. If the reconciled plan then fails ``verify_plan`` AFTER an
    actual stale-triggered regeneration, the persisted plan is cleared
    rather than left standing — ADR-0006: ship no sequence, neither the
    stale original nor the unverified replacement. A verify failure that
    was NOT preceded by a staleness mismatch (the persisted plan, if any,
    was never actually stale) leaves that persisted plan untouched — this
    call simply failed to build a plan, it did not invalidate an existing
    good one.

    The actual reconcile/verify/publish decision runs through
    ``app.plan_ops.republish`` — the same pure core the commit-time
    ``"publish"`` Plan mutation replays against whatever is ACTUALLY
    stored (ADR-0008 amendment: the Plan is user-scoped now and has no
    session-document revision guard, so a concurrent Conversation's
    fresher Plan must be what a regeneration is really decided against,
    not this turn's possibly-stale copy). The two calls agree
    bit-for-bit whenever there is no concurrent writer.
    """
    raw_seq_in = tool_context.state.get("temp:filing_sequencer_seq_in")
    raw_steps = tool_context.state.get("temp:filing_sequencer_steps")
    if not raw_seq_in or not raw_steps:
        return {
            "ok": False,
            "reason": "NO_STEPS",
            "detail": "call sequence_actions and compute_deadlines first",
        }

    from app.sequencer import PlanStep

    seq_in = SequencerIn.model_validate(raw_seq_in)
    steps = tuple(PlanStep.model_validate(step) for step in raw_steps)

    raw_old_plan = tool_context.state.get(PLAN)
    old_plan = Plan.model_validate(raw_old_plan) if raw_old_plan else None
    now = datetime.now(timezone.utc)

    new_state, response = republish(
        old_plan, seq_in=seq_in, steps=steps, plan_id=plan_id, now=now
    )

    if new_state is not None:
        tool_context.state[PLAN] = new_state["plan"]
        tool_context.state[PLAN_SEQ_IN] = new_state["plan_seq_in"]
        tool_context.state[PLAN_ACTIVE] = new_state["plan_active"]
        # Record the mutation (ADR-0008 amendment): the commit-time
        # replay re-runs the SAME republish decision against whatever is
        # ACTUALLY stored, so a concurrent Conversation's write is never
        # silently clobbered by this turn's possibly-stale computation.
        # Append, never assign — a second FILING_SEQUENCER-shaped call
        # sharing this invocation must never replace an earlier one's
        # mutation record.
        mutation = {
            "op": "publish",
            "seq_in": seq_in.model_dump(mode="json"),
            "steps": [step.model_dump(mode="json") for step in steps],
            "plan_id": plan_id,
            "now": now.isoformat(),
        }
        existing = list(tool_context.state.get(PLAN_MUTATIONS) or [])
        tool_context.state[PLAN_MUTATIONS] = existing + [mutation]

    if not response.get("ok"):
        logger.warning(
            "sequencer_verify_plan: %s (%s)",
            response.get("reason"),
            response.get("detail") or response.get("violations"),
        )
    return response


# ---------------------------------------------------------------------------
# FILING_SEQUENCER's structured final output.
# ---------------------------------------------------------------------------


class FilingSequencerOut(BaseModel):
    """FILING_SEQUENCER's single-turn structured result.

    Exactly one of ``plan``, ``held_refusal``, ``unresolved_conflict``, or
    ``no_verified_plan`` is set — DISPATCHER's instruction renders
    whichever is present, never inventing a plan when none of the four
    fired (fails closed to ``no_verified_plan`` framing by omission).
    ``unresolved_conflict`` (issue #44) is distinct from
    ``no_verified_plan``: it names the contested field so DISPATCHER can
    make resolving it — via the one-tap correction — the turn's one
    question, rather than falling back to the Safe Floor. ``delta`` and
    ``was_stale`` (issue #43, ADR-0006) ride alongside a published
    ``plan`` only when it replaced a prior one: ``was_stale`` marks that
    the replacement was triggered by an input-hash mismatch, and
    ``delta`` is the added/removed/carried-DONE step ids
    ``reconcile_plan`` computed — surfaced explicitly rather than a
    silent renumber. ``regeneration_failed`` rides alongside
    ``no_verified_plan`` for the same reason: ADR-0006 requires this
    specific failure — a stale plan's replacement that itself failed
    ``verify_plan`` — to render the Safe Floor PLUS an action card,
    never the Safe Floor alone as a generic "no plan yet".
    """

    plan: Optional[dict[str, Any]] = None
    held_refusal: Optional[dict[str, Any]] = None
    unresolved_conflict: Optional[dict[str, Any]] = None
    no_verified_plan: bool = False
    delta: Optional[dict[str, Any]] = None
    was_stale: bool = False
    regeneration_failed: bool = False


_FILING_SEQUENCER_INSTRUCTION = """\
You are FILING_SEQUENCER. You never talk to the worker directly — your
input is typed arguments only: her country, her tenure situation, and the
grievances she reported. Call your tools in this order:

1. jurisdiction_rules(country) — if the result's status is "held", stop:
   respond with only {"held_refusal": <that tool's card>}. Do not call
   any other tool for a HELD jurisdiction.
2. sequence_actions(country, tenure, grievances) — if ok is false, stop:
   respond with {"held_refusal": <card>} when reason is
   JURISDICTION_HELD, {"unresolved_conflict": {"field": <field>}} when
   reason is UNRESOLVED_CONFLICT (her Case has an unresolved disagreement
   on that field — never a fabricated resolution, never a retry), or
   {"no_verified_plan": true} for any other failure (NO_VERIFIED_PLAN,
   INVALID_INPUT, CASE_COUNTRY_MISMATCH — the country you supplied no
   longer matches her Case; re-derive it from her Case above and call
   sequence_actions again with the corrected country instead of
   retrying the same one). Never retry with the SAME values to force a
   result.
3. compute_deadlines() — attaches each step's deadline. Takes no
   arguments; it reads the rows sequence_actions just built.
4. verify_plan(plan_id) — builds, verifies, and (only if verification
   passes) publishes the Plan in one call. Choose plan_id yourself (a
   short unique string). If ok is false, respond with
   {"no_verified_plan": true}, and if that result's "regeneration_failed"
   is true, copy it into your response verbatim too — never retry to
   force a passing plan.

If verify_plan returns ok=true, respond with {"plan": <the returned plan
object, unchanged>}. If that result also carries a "delta" and/or
"was_stale" key, copy them into your response verbatim alongside "plan"
— never drop them and never invent either when the tool result did not
return them.

Never fabricate a citation, a deadline, or a step. Never call verify_plan
before compute_deadlines, and never call compute_deadlines before
sequence_actions has succeeded. Your only output is the JSON object
matching your response schema — no other text.
"""


def build_filing_sequencer(llm: BaseLlm) -> LlmAgent:
    """Builds FILING_SEQUENCER: ``mode='single_turn'``, closed-enum
    ``input_schema``, the four pure-function tools, and a structured
    ``output_schema``. Attach via ``sub_agents=[...]`` on DISPATCHER —
    google-adk auto-wraps this as ONE tool named ``FILING_SEQUENCER``.
    """
    return LlmAgent(
        name=FILING_SEQUENCER_NAME,
        mode="single_turn",
        model=llm,
        description=(
            "Builds a verified, cited filing Plan for one worker "
            "situation, or the fixed HELD refusal. Never converses."
        ),
        instruction=_FILING_SEQUENCER_INSTRUCTION,
        input_schema=SequencerIn,
        output_schema=FilingSequencerOut,
        tools=[
            sequencer_jurisdiction_rules,
            sequencer_sequence_actions,
            sequencer_compute_deadlines,
            sequencer_verify_plan,
        ],
    )
