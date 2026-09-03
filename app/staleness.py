"""Plan staleness: input-hash mismatch and step expiry (issue #43, ADR-0006).

Two pure functions, run every time a Plan is about to be presented or
regenerated — never DISPATCHER's judgement:

1. :func:`is_input_stale` — ``hash(current_sequencer_in) != plan.input_hash``.
   A field not in :class:`~app.sequencer.SequencerIn` cannot have affected
   the plan, so this check cannot drift out of sync with the sequencer.
   The ordering itself may now be wrong: the caller must stop presenting
   the plan as actionable and show it inactive with the Safe Floor until
   a replacement clears ``publish_plan``.
2. :func:`apply_step_expiry` — wall-clock deadline expiry. Only the
   PENDING steps whose deadline has passed become VOIDED; every other
   step, including DONE ones, stands and she keeps acting on it.

The two triggers are deliberately kept separate: conflating an expired
step with a mismatched plan is the bug ADR-0006 names. Regeneration
(:func:`reconcile_plan`) is never a silent renumber: a DONE step survives
onto its replacement when the same step id still appears, and the delta
of added/removed step ids is surfaced rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.sequencer import Plan, PlanStep, SequencerIn, StepStatus, input_hash

__all__ = [
    "PlanDelta",
    "is_input_stale",
    "apply_step_expiry",
    "mark_step_done",
    "reconcile_plan",
]


def is_input_stale(plan: Plan, seq_in: SequencerIn) -> bool:
    """ADR-0006 check (1): the plan's ordering may no longer be correct.

    Pure. ``True`` when the given (current) :class:`SequencerIn` no
    longer hashes to the value ``plan`` was published against.
    """
    return input_hash(seq_in) != plan.input_hash


def apply_step_expiry(plan: Plan, *, now: datetime) -> Plan:
    """ADR-0006 check (2): wall-clock step expiry.

    Pure; never mutates ``plan``. Only a PENDING step whose
    ``expires_at`` has passed becomes VOIDED — a DONE step and an
    already-VOIDED step are left untouched, and every other PENDING step
    stands. Returns ``plan`` itself (no copy) when nothing changed.
    """
    new_steps: list[PlanStep] = []
    changed = False
    for step in plan.steps:
        if (
            step.status is StepStatus.PENDING
            and step.expires_at is not None
            and datetime.fromisoformat(step.expires_at) <= now
        ):
            new_steps.append(step.model_copy(update={"status": StepStatus.VOIDED}))
            changed = True
        else:
            new_steps.append(step)
    if not changed:
        return plan
    return plan.model_copy(update={"steps": tuple(new_steps)})


def mark_step_done(plan: Plan, step_id: str) -> Plan:
    """Marks one step DONE — the survival behavior needs a real path for
    a step to ever reach DONE in the first place.

    Pure. Idempotent when the step is already DONE. Raises ``ValueError``
    for an unknown step id or one that has already been VOIDED (a voided
    step's deadline has passed; it can never retroactively be completed).
    """
    steps = list(plan.steps)
    for index, step in enumerate(steps):
        if step.id != step_id:
            continue
        if step.status is StepStatus.VOIDED:
            raise ValueError(
                f"step {step_id!r} is VOIDED and cannot be marked DONE"
            )
        if step.status is StepStatus.DONE:
            return plan
        steps[index] = step.model_copy(update={"status": StepStatus.DONE})
        return plan.model_copy(update={"steps": tuple(steps)})
    raise ValueError(f"no such step {step_id!r} in plan {plan.plan_id!r}")


@dataclass(frozen=True)
class PlanDelta:
    """What changed between an old plan and its regenerated replacement.

    Surfaced explicitly (never a silent renumber): ``added`` and
    ``removed`` are step ids that only exist on one side; ``carried_done``
    are step ids that were DONE on the old plan and survived, still DONE,
    onto the new one.
    """

    added: tuple[str, ...]
    removed: tuple[str, ...]
    carried_done: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def reconcile_plan(
    old_plan: Optional[Plan], new_plan: Plan
) -> tuple[Plan, PlanDelta]:
    """Regeneration is never a silent renumber (ADR-0006).

    A DONE step on ``old_plan`` survives onto ``new_plan`` when the same
    step id (the corpus row id — stable across regenerations of the same
    rule row) still appears; the delta of added/removed step ids is
    returned so it can be surfaced, not hidden. Pure; never mutates
    either plan. When ``old_plan`` is ``None`` (no prior plan to
    reconcile against), every step is reported ``added`` and
    ``new_plan`` is returned unchanged.
    """
    if old_plan is None:
        return new_plan, PlanDelta(
            added=tuple(step.id for step in new_plan.steps),
            removed=(),
            carried_done=(),
        )

    old_by_id = {step.id: step for step in old_plan.steps}
    new_ids = {step.id for step in new_plan.steps}

    reconciled_steps: list[PlanStep] = []
    carried_done: list[str] = []
    for step in new_plan.steps:
        old_step = old_by_id.get(step.id)
        if old_step is not None and old_step.status is StepStatus.DONE:
            reconciled_steps.append(
                step.model_copy(update={"status": StepStatus.DONE})
            )
            carried_done.append(step.id)
        else:
            reconciled_steps.append(step)

    added = tuple(step_id for step_id in new_ids if step_id not in old_by_id)
    removed = tuple(step_id for step_id in old_by_id if step_id not in new_ids)
    reconciled = new_plan.model_copy(update={"steps": tuple(reconciled_steps)})
    return reconciled, PlanDelta(
        added=added, removed=removed, carried_done=tuple(carried_done)
    )
