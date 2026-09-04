"""Plan mutation-replay pure suite (ADR-0008 amendment): the Plan
analogue of ``tests/test_case_mutations.py``. Moving the Plan to
user-scoped state removes its session-document revision guard, so
``app.plan_ops.apply_mutations`` must be the thing that keeps a
concurrent Conversation from clobbering a publish, a mark-done, or a
staleness recheck.
"""

from datetime import datetime, timezone

from app.plan_ops import apply_mutations, republish
from app.rules import Citation, Grievance, Jurisdiction, SourceTier, TenureBucket
from app.sequencer import ActionClass, Plan, PlanStep, SequencerIn, StepStatus, build_plan

NOW = datetime(2026, 9, 4, 0, 0, 0, tzinfo=timezone.utc)
T1 = "2026-09-04T00:00:00+00:00"
T2 = "2026-09-04T00:05:00+00:00"
T3 = "2026-09-04T00:10:00+00:00"


def _citation(ref: str = "Art. 1", tier=SourceTier.TIER_1) -> Citation:
    return Citation(
        source_name="Test Source",
        reference=ref,
        url="https://example.org/law",
        tier=tier,
    )


def _step(step_id: str, *, expires_at=None, tier=SourceTier.TIER_1) -> PlanStep:
    return PlanStep(
        id=step_id,
        rule_citation=_citation(tier=tier),
        expires_at=expires_at,
        grievance=Grievance.UNPAID_WAGES,
        file_where="SEnA",
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        tier=tier,
    )


def _seq_in(country=Jurisdiction.SA) -> SequencerIn:
    return SequencerIn(
        country=country,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        grievances=(Grievance.UNPAID_WAGES,),
    )


class TestPublishMutation:
    def test_first_publish_with_no_prior_plan(self):
        mutation = {
            "op": "publish",
            "seq_in": _seq_in().model_dump(mode="json"),
            "steps": [_step("row-1").model_dump(mode="json")],
            "plan_id": "plan-1",
            "now": NOW.isoformat(),
        }
        state = apply_mutations(None, [mutation])
        assert state["plan"]["plan_id"] == "plan-1"
        assert state["plan_active"] is True
        assert state["plan_seq_in"]["country"] == "SA"

    def test_publish_replayed_against_a_fresher_stored_plan_reconciles_done_steps(self):
        # Simulate: the tool computed this mutation against an old plan
        # at version 1, but by commit time a concurrent write already
        # marked step "row-1" DONE on the stored plan. Replaying the
        # publish mutation must carry that DONE mark forward rather than
        # clobbering it with a fresh PENDING step.
        seq_in = _seq_in()
        old_plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=1)
        done_plan = old_plan.model_copy(
            update={
                "steps": (old_plan.steps[0].model_copy(update={"status": StepStatus.DONE}),)
            }
        )
        stored = {
            "plan": done_plan.model_dump(mode="json"),
            "plan_seq_in": seq_in.model_dump(mode="json"),
            "plan_active": True,
        }
        mutation = {
            "op": "publish",
            "seq_in": seq_in.model_dump(mode="json"),
            "steps": [_step("row-1").model_dump(mode="json")],
            "plan_id": "plan-1",
            "now": NOW.isoformat(),
        }
        state = apply_mutations(stored, [mutation])
        assert state["plan"]["steps"][0]["status"] == "DONE"
        assert state["plan"]["version"] == 2

    def test_missing_fields_are_a_no_op(self):
        state = apply_mutations(None, [{"op": "publish", "now": T1}])
        assert state == {"plan": None, "plan_seq_in": None, "plan_active": None}


class TestMarkStepDoneMutation:
    def test_marks_the_named_step_done(self):
        seq_in = _seq_in()
        plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=1)
        stored = {"plan": plan.model_dump(mode="json"), "plan_seq_in": None, "plan_active": True}
        mutation = {"op": "mark_step_done", "plan_id": "plan-1", "step_id": "row-1", "now": T1}
        state = apply_mutations(stored, [mutation])
        assert state["plan"]["steps"][0]["status"] == "DONE"

    def test_plan_id_mismatch_is_a_no_op(self):
        seq_in = _seq_in()
        plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=1)
        stored = {"plan": plan.model_dump(mode="json"), "plan_seq_in": None, "plan_active": True}
        # The stored Plan has moved on (a concurrent regeneration since
        # this mutation was recorded) — applying it would mislabel a
        # step on a Plan it was never actually completed on.
        mutation = {"op": "mark_step_done", "plan_id": "stale-plan-id", "step_id": "row-1", "now": T1}
        state = apply_mutations(stored, [mutation])
        assert state["plan"]["steps"][0]["status"] == "PENDING"

    def test_unknown_step_id_is_a_no_op(self):
        seq_in = _seq_in()
        plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=1)
        stored = {"plan": plan.model_dump(mode="json"), "plan_seq_in": None, "plan_active": True}
        mutation = {"op": "mark_step_done", "plan_id": "plan-1", "step_id": "no-such-row", "now": T1}
        state = apply_mutations(stored, [mutation])
        assert state["plan"]["steps"][0]["status"] == "PENDING"

    def test_no_stored_plan_is_a_no_op(self):
        state = apply_mutations(None, [{"op": "mark_step_done", "plan_id": "p", "step_id": "s", "now": T1}])
        assert state["plan"] is None


class TestRecheckStalenessMutation:
    def test_expires_pending_step_past_deadline(self):
        seq_in = _seq_in()
        past = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        plan = build_plan(seq_in, (_step("row-1", expires_at=past),), plan_id="plan-1", version=1)
        stored = {"plan": plan.model_dump(mode="json"), "plan_seq_in": seq_in.model_dump(mode="json"), "plan_active": True}
        mutation = {"op": "recheck_staleness", "country": "SA", "now": NOW.isoformat()}
        state = apply_mutations(stored, [mutation])
        assert state["plan"]["steps"][0]["status"] == "VOIDED"

    def test_country_change_marks_plan_inactive_against_fresh_stored_seq_in(self):
        seq_in = _seq_in(Jurisdiction.SA)
        plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=1)
        stored = {"plan": plan.model_dump(mode="json"), "plan_seq_in": seq_in.model_dump(mode="json"), "plan_active": True}
        mutation = {"op": "recheck_staleness", "country": "QA", "now": NOW.isoformat()}
        state = apply_mutations(stored, [mutation])
        assert state["plan_active"] is False

    def test_race_a_fresher_stored_plan_is_what_gets_evaluated(self):
        # Conversation A publishes a fresh, matching Plan; Conversation
        # B's staleness recheck was computed against an OLDER Plan
        # (different seq_in) at ITS turn's start. Replayed against the
        # FRESH stored Plan (A's), the recheck must find it NOT stale —
        # the whole point of moving this to a commit-time mutation.
        seq_in = _seq_in(Jurisdiction.SA)
        fresh_plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=3)
        stored = {
            "plan": fresh_plan.model_dump(mode="json"),
            "plan_seq_in": seq_in.model_dump(mode="json"),
            "plan_active": True,
        }
        # B's mutation only carries the country it resolved this turn —
        # never a seq_in snapshot — so replay always compares against
        # the freshly-stored plan_seq_in, not a value B captured itself.
        mutation = {"op": "recheck_staleness", "country": "SA", "now": NOW.isoformat()}
        state = apply_mutations(stored, [mutation])
        assert state["plan_active"] is True

    def test_no_country_leaves_plan_active_untouched(self):
        seq_in = _seq_in()
        plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=1)
        stored = {"plan": plan.model_dump(mode="json"), "plan_seq_in": seq_in.model_dump(mode="json"), "plan_active": True}
        mutation = {"op": "recheck_staleness", "country": None, "now": NOW.isoformat()}
        state = apply_mutations(stored, [mutation])
        assert state["plan_active"] is True

    def test_no_stored_plan_is_a_no_op(self):
        state = apply_mutations(None, [{"op": "recheck_staleness", "country": "SA", "now": NOW.isoformat()}])
        assert state["plan"] is None


class TestUnknownMutationLeavesPlanIntact:
    def test_unknown_op_is_a_no_op(self):
        seq_in = _seq_in()
        plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=1)
        stored = {"plan": plan.model_dump(mode="json"), "plan_seq_in": None, "plan_active": True}
        state = apply_mutations(stored, [{"op": "delete_everything", "now": T1}])
        assert state["plan"] == stored["plan"]

    def test_non_dict_entries_ignored(self):
        state = apply_mutations(None, ["a string", 1, None])
        assert state == {"plan": None, "plan_seq_in": None, "plan_active": None}

    def test_malformed_payload_does_not_raise(self):
        state = apply_mutations(
            None, [{"op": "publish", "seq_in": {"bad": "data"}, "steps": [{}], "plan_id": "p", "now": "not-a-date"}]
        )
        assert state == {"plan": None, "plan_seq_in": None, "plan_active": None}


class TestPurity:
    def test_input_state_not_mutated(self):
        import copy

        seq_in = _seq_in()
        plan = build_plan(seq_in, (_step("row-1"),), plan_id="plan-1", version=1)
        stored = {"plan": plan.model_dump(mode="json"), "plan_seq_in": None, "plan_active": True}
        snapshot = copy.deepcopy(stored)
        apply_mutations(stored, [{"op": "mark_step_done", "plan_id": "plan-1", "step_id": "row-1", "now": T1}])
        assert stored == snapshot


class TestRepublishSharedCore:
    """Sanity: the shared core FILING_SEQUENCER's tool and the mutation
    replay both call agrees with itself when given the same inputs
    twice (no hidden non-determinism to drift on)."""

    def test_deterministic(self):
        seq_in = _seq_in()
        steps = (_step("row-1"),)
        state1, response1 = republish(None, seq_in=seq_in, steps=steps, plan_id="p", now=NOW)
        state2, response2 = republish(None, seq_in=seq_in, steps=steps, plan_id="p", now=NOW)
        assert state1 == state2
        assert response1 == response2
