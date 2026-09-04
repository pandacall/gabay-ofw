"""DISPATCHER's tools: the only doors to contact data (issue #39).

Every tool resolves the user's country server-side from her Case — the
model never supplies a country or a phone number. ``action_card`` takes
immutable-directory KEYS, never number strings, resolved server-side and
filtered for dialability from her country. Every result crosses
ROUTING_GUARD, which filters rows by channel on the way back.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from google.adk.tools import ToolContext

from app.directory import (
    office_directory_rows,
    resolve_case_country,
    resolve_keys,
)
from app.safe_floor import SafeFloorReason, build_card, is_emergency_conversation
from app.sequencer import Plan
from app.staleness import mark_step_done
from app.state_keys import CASE, PLAN, PLAN_ACTIVE, PLAN_MUTATIONS

logger = logging.getLogger(__name__)


def _case(tool_context: ToolContext) -> dict[str, Any] | None:
    case = tool_context.state.get(CASE)
    return case if isinstance(case, dict) else None


def office_directory(tool_context: ToolContext) -> dict[str, Any]:
    """Lists the real offices that can help the user, for her country.

    Returns channel-tagged rows: Migrant Workers Office (MWO), Philippine
    embassy Assistance-to-Nationals (ATN), and Philippine-side hotlines.
    Each row has a ``key`` — pass keys to ``action_card`` to build a
    contact card. Numbers marked ``manila_relay`` are for someone in the
    Philippines to call on the user's behalf; they do not dial from her
    country.
    """
    case = _case(tool_context)
    country = resolve_case_country(case)
    return {"rows": office_directory_rows(country)}


def action_card(keys: list[str], tool_context: ToolContext) -> dict[str, Any]:
    """Builds a contact card from office_directory row keys.

    Args:
        keys: Directory keys exactly as returned by ``office_directory``
            (for example ``["mwo_riyadh", "owwa_1348"]``). Never phone
            numbers — numbers are resolved server-side from the immutable
            directory and filtered for dialability from the user's
            country. Unknown keys are dropped, never guessed.
    """
    case = _case(tool_context)
    country = resolve_case_country(case)
    safe_keys = [key for key in keys if isinstance(key, str)]
    return {
        "card": {
            "type": "action_card",
            "country": country.value,
            "contacts": resolve_keys(safe_keys, country),
        }
    }


def safe_floor_card(reason: str, tool_context: ToolContext) -> dict[str, Any]:
    """Renders the user's country's fixed Safe Floor card.

    Call this whenever no verified plan can be shown: you cannot confirm
    the right filing order, her country's sequence is not verified, or
    her facts changed. The card is fixed and code-owned — frame it warmly
    in your own words, but the contacts and reason line come from the
    card itself.

    Args:
        reason: One of ``NO_VERIFIED_PLAN`` (no verified plan exists for
            her situation), ``JURISDICTION_HELD`` (her country's filing
            sequence is not verified), ``FACTS_CHANGED`` (her facts
            changed and the plan needs updating).
    """
    case = _case(tool_context)
    country = resolve_case_country(case)
    try:
        parsed = SafeFloorReason(reason)
    except ValueError:
        # Fail closed: an unrecognized reason renders the most honest line.
        logger.warning("safe_floor_card: unknown reason %r", reason)
        parsed = SafeFloorReason.NO_VERIFIED_PLAN
    if parsed is SafeFloorReason.SERVICE_DOWN:
        # SERVICE_DOWN is the hard-fallback path's reason, not a model choice.
        parsed = SafeFloorReason.NO_VERIFIED_PLAN
    return {
        "card": build_card(
            country,
            reason=parsed,
            imminent_danger=is_emergency_conversation(tool_context.state),
        )
    }


def mark_plan_step_done(
    plan_id: str, step_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Marks one step of her CURRENT filing Plan as DONE (issue #43).

    Call this whenever she reports having already completed a filing
    step (she filed the SEnA request, she already reported the huroob
    case). This is the only path a step ever reaches DONE — without it,
    a regenerated plan would have nothing to carry forward and she would
    lose her place every time her facts are corrected.

    Args:
        plan_id: The ``plan_id`` of her current Plan, exactly as it was
            shown to her — a mismatch means the plan has since changed
            and this call is refused rather than silently applied to the
            wrong plan.
        step_id: The step's own id, exactly as shown on that step.
    """
    raw_plan = tool_context.state.get(PLAN)
    if not raw_plan:
        return {"ok": False, "reason": "NO_ACTIVE_PLAN"}
    if tool_context.state.get(PLAN_ACTIVE) is False:
        # ADR-0006: an inactive (stale) plan stops being presented as
        # actionable. Advancing one of its steps to DONE would still be
        # treating it as current — code-owned, not left to the model
        # noticing the plan is inactive and declining to call this.
        return {"ok": False, "reason": "PLAN_INACTIVE"}
    plan = Plan.model_validate(raw_plan)
    if plan.plan_id != plan_id:
        return {"ok": False, "reason": "PLAN_MISMATCH"}
    try:
        updated = mark_step_done(plan, step_id)
    except ValueError as exc:
        return {"ok": False, "reason": "STEP_NOT_DONE_ELIGIBLE", "detail": str(exc)}
    tool_context.state[PLAN] = updated.model_dump(mode="json")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Append, never assign (ADR-0008): two tool calls sharing one
    # invocation must never have the second's mutation record replace
    # the first's — read whatever this turn has already accumulated and
    # add to it.
    existing = list(tool_context.state.get(PLAN_MUTATIONS) or [])
    tool_context.state[PLAN_MUTATIONS] = existing + [
        {"op": "mark_step_done", "plan_id": plan_id, "step_id": step_id, "now": now}
    ]
    return {"card": {"type": "plan", **updated.model_dump(mode="json")}}
