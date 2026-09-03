"""Plan staleness pure-function suite (issue #43, ADR-0006, CI-gating).

Seconds-fast, no infrastructure, no API key. Covers the two distinct
staleness triggers and their distinct consequences (hash mismatch marks a
plan inactive; expiry voids only expired steps), DONE-step survival with a
surfaced delta on regeneration, and the mark-DONE path that makes survival
real.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.rules import Grievance, Jurisdiction, TenureBucket
from app.sequencer import (
    Plan,
    PlanStep,
    SequencerIn,
    StepStatus,
    build_plan,
    compute_deadlines,
    sequence_actions,
)
from app.staleness import (
    PlanDelta,
    apply_step_expiry,
    is_input_stale,
    mark_step_done,
    reconcile_plan,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

SA_WAGES = SequencerIn(
    country=Jurisdiction.SA,
    tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
    grievances=(Grievance.UNPAID_WAGES,),
)
QA_WAGES = SequencerIn(
    country=Jurisdiction.QA,
    tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
    grievances=(Grievance.UNPAID_WAGES,),
)


def _plan(seq_in: SequencerIn, *, plan_id: str = "plan-1", version: int = 1) -> Plan:
    rows = sequence_actions(seq_in)
    steps = compute_deadlines(rows, now=NOW)
    return build_plan(seq_in, steps, plan_id=plan_id, version=version)


def _with_step_status(plan: Plan, step_id: str, status: StepStatus) -> Plan:
    steps = tuple(
        step.model_copy(update={"status": status}) if step.id == step_id else step
        for step in plan.steps
    )
    return plan.model_copy(update={"steps": steps})


# ---------------------------------------------------------------------------
# is_input_stale — check (1): hash mismatch.
# ---------------------------------------------------------------------------


class TestIsInputStale:
    def test_same_input_is_not_stale(self):
        plan = _plan(SA_WAGES)
        assert is_input_stale(plan, SA_WAGES) is False

    def test_a_changed_field_is_stale(self):
        plan = _plan(SA_WAGES)
        # Correcting tenure across a rule boundary changes the hash.
        corrected = SA_WAGES.model_copy(
            update={"tenure": TenureBucket.DEPARTED_COUNTRY}
        )
        assert is_input_stale(plan, corrected) is True

    def test_a_different_country_is_stale(self):
        plan = _plan(SA_WAGES)
        assert is_input_stale(plan, QA_WAGES) is True


# ---------------------------------------------------------------------------
# apply_step_expiry — check (2): only expired PENDING steps are voided.
# ---------------------------------------------------------------------------


class TestApplyStepExpiry:
    def test_a_pending_step_past_its_deadline_is_voided(self):
        plan = _plan(QA_WAGES)  # QA wages: Tier-1 hard deadline countdown.
        step = plan.steps[0]
        assert step.expires_at is not None
        past = datetime.fromisoformat(step.expires_at) + timedelta(days=1)
        voided = apply_step_expiry(plan, now=past)
        assert voided.steps[0].status is StepStatus.VOIDED

    def test_a_pending_step_before_its_deadline_stands(self):
        plan = _plan(QA_WAGES)
        step = plan.steps[0]
        before = datetime.fromisoformat(step.expires_at) - timedelta(days=1)
        untouched = apply_step_expiry(plan, now=before)
        assert untouched.steps[0].status is StepStatus.PENDING

    def test_a_step_with_no_expires_at_is_never_voided(self):
        plan = _plan(SA_WAGES)  # SA wages: Tier-2, no countdown.
        assert plan.steps[0].expires_at is None
        result = apply_step_expiry(plan, now=NOW + timedelta(days=3650))
        assert result.steps[0].status is StepStatus.PENDING

    def test_expiry_never_touches_a_done_step(self):
        plan = _plan(QA_WAGES)
        done = _with_step_status(plan, plan.steps[0].id, StepStatus.DONE)
        past = datetime.fromisoformat(plan.steps[0].expires_at) + timedelta(days=1)
        result = apply_step_expiry(done, now=past)
        assert result.steps[0].status is StepStatus.DONE

    def test_expiry_leaves_other_pending_steps_standing(self):
        # Multi-grievance plan: one step with a hard deadline, one without.
        seq_in = QA_WAGES.model_copy(
            update={
                "grievances": (
                    Grievance.PHYSICAL_ABUSE_OR_DANGER,
                    Grievance.UNPAID_WAGES,
                )
            }
        )
        plan = _plan(seq_in)
        wages_step = next(s for s in plan.steps if s.grievance is Grievance.UNPAID_WAGES)
        past = datetime.fromisoformat(wages_step.expires_at) + timedelta(days=1)
        result = apply_step_expiry(plan, now=past)
        by_id = {step.id: step for step in result.steps}
        assert by_id[wages_step.id].status is StepStatus.VOIDED
        other = next(s for s in result.steps if s.id != wages_step.id)
        assert other.status is StepStatus.PENDING

    def test_no_change_returns_the_same_plan_object(self):
        plan = _plan(SA_WAGES)
        assert apply_step_expiry(plan, now=NOW) is plan


# ---------------------------------------------------------------------------
# The two triggers produce DISTINCT consequences — never conflated.
# ---------------------------------------------------------------------------


class TestDistinctConsequences:
    def test_expiry_alone_never_marks_the_plan_input_stale(self):
        plan = _plan(QA_WAGES)
        future = datetime.fromisoformat(plan.steps[0].expires_at) + timedelta(days=1)
        voided = apply_step_expiry(plan, now=future)
        # The steps changed (expiry), but the SAME SequencerIn built this
        # plan — input-hash staleness is a completely separate question.
        assert is_input_stale(voided, QA_WAGES) is False

    def test_input_mismatch_alone_never_voids_steps(self):
        plan = _plan(SA_WAGES)
        assert is_input_stale(plan, QA_WAGES) is True
        # is_input_stale is a pure predicate: it never mutates the plan
        # it was asked about.
        assert all(step.status is StepStatus.PENDING for step in plan.steps)


# ---------------------------------------------------------------------------
# mark_step_done — the path DONE-survival needs to be real.
# ---------------------------------------------------------------------------


class TestMarkStepDone:
    def test_marks_a_pending_step_done(self):
        plan = _plan(SA_WAGES)
        step_id = plan.steps[0].id
        result = mark_step_done(plan, step_id)
        assert result.steps[0].status is StepStatus.DONE

    def test_is_idempotent_on_an_already_done_step(self):
        plan = _plan(SA_WAGES)
        step_id = plan.steps[0].id
        once = mark_step_done(plan, step_id)
        twice = mark_step_done(once, step_id)
        assert twice.steps[0].status is StepStatus.DONE

    def test_raises_for_an_unknown_step_id(self):
        plan = _plan(SA_WAGES)
        with pytest.raises(ValueError):
            mark_step_done(plan, "no-such-step")

    def test_raises_for_a_voided_step(self):
        plan = _plan(QA_WAGES)
        voided = _with_step_status(plan, plan.steps[0].id, StepStatus.VOIDED)
        with pytest.raises(ValueError):
            mark_step_done(voided, plan.steps[0].id)


# ---------------------------------------------------------------------------
# reconcile_plan — regeneration is never a silent renumber.
# ---------------------------------------------------------------------------


class TestReconcilePlan:
    def test_no_prior_plan_reports_every_step_as_added(self):
        new_plan = _plan(SA_WAGES)
        reconciled, delta = reconcile_plan(None, new_plan)
        assert reconciled is new_plan
        assert set(delta.added) == {step.id for step in new_plan.steps}
        assert delta.removed == ()
        assert delta.carried_done == ()

    def test_a_done_step_survives_regeneration(self):
        old_plan = _plan(SA_WAGES, plan_id="plan-1", version=1)
        done_id = old_plan.steps[0].id
        old_plan = mark_step_done(old_plan, done_id)

        # Regeneration from a corrected fact: she's now also reporting her
        # passport withheld. The original wages row (same step id) still
        # applies — she may have already filed it (DONE) — and a new
        # step is added alongside it.
        corrected = SA_WAGES.model_copy(
            update={
                "grievances": (
                    Grievance.UNPAID_WAGES,
                    Grievance.PASSPORT_WITHHELD,
                )
            }
        )
        assert is_input_stale(old_plan, corrected) is True
        rows = sequence_actions(corrected)
        steps = compute_deadlines(rows, now=NOW)
        new_plan = build_plan(corrected, steps, plan_id="plan-1", version=2)

        reconciled, delta = reconcile_plan(old_plan, new_plan)
        carried_step = next(s for s in reconciled.steps if s.id == done_id)
        assert carried_step.status is StepStatus.DONE
        assert done_id in delta.carried_done
        assert len(delta.added) == 1

    def test_delta_surfaces_added_and_removed_steps(self):
        old_plan = _plan(SA_WAGES)
        wider = SA_WAGES.model_copy(
            update={
                "grievances": (
                    Grievance.UNPAID_WAGES,
                    Grievance.PASSPORT_WITHHELD,
                )
            }
        )
        rows = sequence_actions(wider)
        steps = compute_deadlines(rows, now=NOW)
        new_plan = build_plan(wider, steps, plan_id="plan-1", version=2)

        reconciled, delta = reconcile_plan(old_plan, new_plan)
        assert len(reconciled.steps) == 2
        assert len(delta.added) == 1
        assert delta.removed == ()

    def test_a_dropped_grievance_surfaces_as_removed(self):
        wider = SA_WAGES.model_copy(
            update={
                "grievances": (
                    Grievance.UNPAID_WAGES,
                    Grievance.PASSPORT_WITHHELD,
                )
            }
        )
        old_plan = _plan(wider)
        rows = sequence_actions(SA_WAGES)
        steps = compute_deadlines(rows, now=NOW)
        new_plan = build_plan(SA_WAGES, steps, plan_id="plan-1", version=2)

        reconciled, delta = reconcile_plan(old_plan, new_plan)
        assert len(reconciled.steps) == 1
        assert len(delta.removed) == 1
        assert delta.added == ()

    def test_no_change_yields_an_empty_delta(self):
        old_plan = _plan(SA_WAGES)
        new_plan = _plan(SA_WAGES, version=2)
        reconciled, delta = reconcile_plan(old_plan, new_plan)
        assert delta.changed is False
        assert delta.carried_done == ()

    def test_reconcile_never_mutates_the_inputs(self):
        old_plan = _plan(SA_WAGES)
        old_plan = mark_step_done(old_plan, old_plan.steps[0].id)
        new_plan = _plan(SA_WAGES, version=2)
        reconcile_plan(old_plan, new_plan)
        assert old_plan.steps[0].status is StepStatus.DONE
        assert new_plan.steps[0].status is StepStatus.PENDING


class TestPlanDelta:
    def test_changed_is_false_when_nothing_added_or_removed(self):
        delta = PlanDelta(added=(), removed=(), carried_done=("a",))
        assert delta.changed is False

    def test_changed_is_true_when_something_added(self):
        delta = PlanDelta(added=("a",), removed=(), carried_done=())
        assert delta.changed is True
