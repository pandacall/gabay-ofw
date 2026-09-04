"""Plan mutation ops (ADR-0008 amendment): a Plan write persists the
mutation that produced it too, not a merged blob — the exact same fix
``app.case.apply_mutations`` gives the Case, applied to the Plan.

Moving ``plan`` / ``plan_seq_in`` / ``plan_active`` to ``user:`` scope
(ADR-0008) removes their only prior concurrency guard: they used to live
in per-session state, protected by the session document's ``revision``
check, but user-scoped state has no revision guard at all. Without this
module, two Conversations racing would be able to clobber each other:

* the plan-staleness recheck (``app.agent._recheck_plan_staleness``) runs
  every turn and writes ``plan_active`` from whatever Plan copy it loaded
  at THAT turn's start — a second Conversation's stale copy could
  overwrite ``plan_active=True`` a first Conversation just verified with
  a stale ``False``;
* marking a step done writes the entire Plan blob, so a stale writer
  could silently discard a newer version and its completed steps;
* invalidating a Plan on a failed regeneration could null out a Plan
  another Conversation had just published.

``republish`` is the single pure core for a regeneration decision, shared
by FILING_SEQUENCER's tool (``app.sequencer_agent.sequencer_verify_plan``,
which needs an answer THIS turn, computed against the turn-start Plan)
and ``apply_mutations`` below (which recomputes the SAME decision against
whatever is ACTUALLY stored at commit time). With no concurrent writer —
the common case — the two inputs are identical and the two calls agree
bit-for-bit; the shared core exists so they can never quietly drift
apart.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.sequencer import (
    Plan,
    PlanNotVerifiedError,
    PlanStep,
    SequencerIn,
    build_plan,
    plan_hash,
    publish_plan,
    verify_plan,
)
from app.staleness import (
    apply_step_expiry,
    is_input_stale,
    mark_step_done,
    reconcile_plan,
)

#: The mutation shapes this build understands, mirroring
#: ``app.case.MUTATION_OPS``.
MUTATION_OPS = frozenset({"publish", "mark_step_done", "recheck_staleness"})

_INVALIDATED_STATE: dict[str, Any] = {
    "plan": None,
    "plan_seq_in": None,
    "plan_active": False,
}


def republish(
    old_plan: Optional[Plan],
    *,
    seq_in: SequencerIn,
    steps: tuple[PlanStep, ...],
    plan_id: str,
    now: datetime,
) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    """Reconciles, verifies, and (on success) publishes a Plan against
    ``old_plan`` — whichever Plan the caller supplies: the turn-start
    snapshot (FILING_SEQUENCER's tool) or the freshly-read stored Plan
    (a commit-time mutation replay).

    Returns ``(new_plan_state, response)``:

    * ``new_plan_state`` is ``None`` when nothing about the persisted
      Plan should change — a verify/publish failure that was NOT
      preceded by a staleness mismatch, so the existing Plan (if any) is
      left exactly as it was. Otherwise it is a fresh
      ``{"plan", "plan_seq_in", "plan_active"}`` dict to write: either a
      successful publish, or an ADR-0006 invalidation (a regeneration
      that itself failed to verify, triggered by an actually-stale
      Plan).
    * ``response`` is FILING_SEQUENCER's tool-shaped result, unchanged
      from what ``sequencer_verify_plan`` returned before this refactor.

    Pure: never mutates ``old_plan`` or ``steps``.
    """
    was_stale = old_plan is not None and is_input_stale(old_plan, seq_in)
    version = (old_plan.version + 1) if old_plan is not None else 1
    fresh_plan = build_plan(seq_in, steps, plan_id=plan_id, version=version)
    plan, delta = reconcile_plan(old_plan, fresh_plan)
    plan = apply_step_expiry(plan, now=now)

    result = verify_plan(plan)
    if not result.ok:
        return (
            dict(_INVALIDATED_STATE) if was_stale else None,
            {
                "ok": False,
                "reason": "VERIFY_FAILED",
                "violations": list(result.violations),
                "regeneration_failed": was_stale,
            },
        )

    cleared_hashes = frozenset({plan_hash(plan)})
    try:
        published = publish_plan(plan, cleared_hashes=cleared_hashes)
    except PlanNotVerifiedError as exc:  # defensive: should be unreachable
        return (
            dict(_INVALIDATED_STATE) if was_stale else None,
            {"ok": False, "reason": "PUBLISH_REFUSED", "detail": str(exc)},
        )

    new_state = {
        "plan": published.model_dump(mode="json"),
        "plan_seq_in": seq_in.model_dump(mode="json"),
        "plan_active": True,
    }
    response: dict[str, Any] = {
        "ok": True,
        "plan": published.model_dump(mode="json"),
    }
    if was_stale:
        response["was_stale"] = True
    if old_plan is not None and (delta.changed or delta.carried_done):
        response["delta"] = {
            "added": list(delta.added),
            "removed": list(delta.removed),
            "carried_done": list(delta.carried_done),
        }
    return new_state, response


# ---------------------------------------------------------------------------
# Mutation replay (mirrors app.case.apply_mutations).
# ---------------------------------------------------------------------------


def _plan_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(raw) if raw else {}
    base.setdefault("plan", None)
    base.setdefault("plan_seq_in", None)
    base.setdefault("plan_active", None)
    return base


def apply_mutations(
    plan_state: dict[str, Any] | None, mutations: list[Any] | None
) -> dict[str, Any]:
    """Replays recorded Plan mutations onto ``{"plan", "plan_seq_in",
    "plan_active"}``, in order, against whatever is ACTUALLY stored.

    Mutation shapes:

        {"op": "publish", "seq_in": <SequencerIn dict>,
         "steps": [<PlanStep dict>, ...], "plan_id": ..., "now": ...}
        {"op": "mark_step_done", "plan_id": ..., "step_id": ..., "now": ...}
        {"op": "recheck_staleness", "country": <Jurisdiction value or
         None>, "now": ...}

    Pure: neither ``plan_state`` nor any mutation entry is mutated. A
    non-dict entry, an unrecognised ``"op"``, or a payload this build
    cannot make sense of leaves the accumulated state UNTOUCHED for that
    entry — never raises, never clears an existing Plan.
    """
    state = _plan_state(plan_state)
    for mutation in mutations or []:
        if not isinstance(mutation, dict):
            continue
        op = mutation.get("op")
        if op not in MUTATION_OPS:
            continue
        try:
            if op == "publish":
                state = _apply_publish(state, mutation)
            elif op == "mark_step_done":
                state = _apply_mark_step_done(state, mutation)
            elif op == "recheck_staleness":
                state = _apply_recheck_staleness(state, mutation)
        except Exception:
            # A malformed mutation payload (bad ISO timestamp, a Plan
            # dict that no longer validates, ...) is exactly as harmless
            # to skip as an unrecognised op: never lose the rest of the
            # Plan over one bad entry.
            continue
    return state


def _apply_publish(state: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    seq_in_raw = mutation.get("seq_in")
    steps_raw = mutation.get("steps")
    plan_id = mutation.get("plan_id")
    now_raw = mutation.get("now")
    if not seq_in_raw or not steps_raw or not plan_id or not now_raw:
        return state
    seq_in = SequencerIn.model_validate(seq_in_raw)
    steps = tuple(PlanStep.model_validate(step) for step in steps_raw)
    now = datetime.fromisoformat(now_raw)
    old_raw = state.get("plan")
    old_plan = Plan.model_validate(old_raw) if old_raw else None
    new_state, _response = republish(
        old_plan, seq_in=seq_in, steps=steps, plan_id=plan_id, now=now
    )
    if new_state is None:
        return state
    return {**state, **new_state}


def _apply_mark_step_done(
    state: dict[str, Any], mutation: dict[str, Any]
) -> dict[str, Any]:
    plan_id = mutation.get("plan_id")
    step_id = mutation.get("step_id")
    raw_plan = state.get("plan")
    if not plan_id or not step_id or not raw_plan:
        return state
    plan = Plan.model_validate(raw_plan)
    if plan.plan_id != plan_id:
        # The stored Plan has moved on since this mark was recorded —
        # applying it to the wrong Plan would silently mislabel a step
        # that was never actually completed on THIS Plan.
        return state
    try:
        updated = mark_step_done(plan, step_id)
    except ValueError:
        return state
    return {**state, "plan": updated.model_dump(mode="json")}


def _apply_recheck_staleness(
    state: dict[str, Any], mutation: dict[str, Any]
) -> dict[str, Any]:
    now_raw = mutation.get("now")
    raw_plan = state.get("plan")
    if not now_raw or not raw_plan:
        return state
    plan = Plan.model_validate(raw_plan)
    now = datetime.fromisoformat(now_raw)
    voided = apply_step_expiry(plan, now=now)
    state = {**state, "plan": voided.model_dump(mode="json")}

    country = mutation.get("country")
    raw_seq_in = state.get("plan_seq_in")
    if country is None or not raw_seq_in:
        # No country signal, or no persisted SequencerIn to compare
        # against: leave plan_active exactly as it is stored.
        return state
    current_seq_in = SequencerIn.model_validate({**raw_seq_in, "country": country})
    return {**state, "plan_active": not is_input_stale(voided, current_seq_in)}
