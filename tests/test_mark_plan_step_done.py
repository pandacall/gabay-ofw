"""``mark_plan_step_done`` tool tests (issue #43, ADR-0006).

The path a step needs to reach DONE in the first place, so DONE-step
survival across a regeneration is real rather than theoretical. No model,
no HTTP — a minimal ``ToolContext`` stand-in exposing only ``.state``,
matching the pattern in ``tests/test_filing_sequencer_agent.py``.
"""

from __future__ import annotations

from app.rules import Grievance, Jurisdiction, TenureBucket
from app.sequencer import SequencerIn, build_plan, compute_deadlines, sequence_actions
from app.state_keys import PLAN, PLAN_ACTIVE
from app.tools import mark_plan_step_done


class _FakeState(dict):
    pass


class _FakeToolContext:
    def __init__(self):
        self.state = _FakeState()


def _published_plan(*, plan_id: str = "plan-1"):
    seq_in = SequencerIn(
        country=Jurisdiction.SA,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        grievances=(Grievance.UNPAID_WAGES,),
    )
    rows = sequence_actions(seq_in)
    from datetime import datetime, timezone

    steps = compute_deadlines(rows, now=datetime.now(timezone.utc))
    return build_plan(seq_in, steps, plan_id=plan_id)


class TestMarkPlanStepDone:
    def test_marks_a_step_done_and_persists_it(self):
        ctx = _FakeToolContext()
        plan = _published_plan()
        ctx.state[PLAN] = plan.model_dump(mode="json")
        step_id = plan.steps[0].id

        result = mark_plan_step_done(plan.plan_id, step_id, ctx)
        assert result["card"]["type"] == "plan"
        by_id = {step["id"]: step for step in result["card"]["steps"]}
        assert by_id[step_id]["status"] == "DONE"
        assert ctx.state[PLAN]["steps"][0]["status"] == "DONE"

    def test_no_active_plan_refuses(self):
        ctx = _FakeToolContext()
        result = mark_plan_step_done("plan-1", "some-step", ctx)
        assert result == {"ok": False, "reason": "NO_ACTIVE_PLAN"}

    def test_plan_id_mismatch_refuses(self):
        ctx = _FakeToolContext()
        plan = _published_plan(plan_id="plan-1")
        ctx.state[PLAN] = plan.model_dump(mode="json")

        result = mark_plan_step_done("plan-2", plan.steps[0].id, ctx)
        assert result == {"ok": False, "reason": "PLAN_MISMATCH"}
        # The persisted plan is left untouched.
        assert ctx.state[PLAN]["steps"][0]["status"] == "PENDING"

    def test_unknown_step_id_refuses_without_mutating_state(self):
        ctx = _FakeToolContext()
        plan = _published_plan()
        ctx.state[PLAN] = plan.model_dump(mode="json")

        result = mark_plan_step_done(plan.plan_id, "no-such-step", ctx)
        assert result["ok"] is False
        assert result["reason"] == "STEP_NOT_DONE_ELIGIBLE"
        assert ctx.state[PLAN]["steps"][0]["status"] == "PENDING"

    def test_inactive_plan_refuses(self):
        # ADR-0006 (issue #43): an inactive (stale) plan stops being
        # presented as actionable — advancing one of its steps to DONE
        # would still be treating it as current.
        ctx = _FakeToolContext()
        plan = _published_plan()
        ctx.state[PLAN] = plan.model_dump(mode="json")
        ctx.state[PLAN_ACTIVE] = False

        result = mark_plan_step_done(plan.plan_id, plan.steps[0].id, ctx)
        assert result == {"ok": False, "reason": "PLAN_INACTIVE"}
        assert ctx.state[PLAN]["steps"][0]["status"] == "PENDING"
