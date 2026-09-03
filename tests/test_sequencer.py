"""FILING_SEQUENCER pure-function suite (issue #42, PRD #34 testing decision).

CI-gate style: seconds-fast, no infrastructure, no API key. The 12-fixture
suite (6 SA, 4 QA, 2 KW/AE refusals) is asserted directly against
``sequence_actions`` / ``compute_deadlines`` / ``verify_plan``. Refusal
fixtures are first-class: KW/AE raises before any sequence is produced;
an unresolved verify violation at the repair bound emits no sequence
either. A structural test proves ``publish_plan`` refuses a tampered hash.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.rules import ActionClass, Grievance, Jurisdiction, SourceTier, TenureBucket
from app.sequencer import (
    JurisdictionHeldError,
    NoVerifiedPlanError,
    PlanNotVerifiedError,
    PlanStep,
    SequencerIn,
    StepStatus,
    build_plan,
    compute_deadlines,
    held_refusal_card,
    input_hash,
    jurisdiction_rules,
    plan_hash,
    publish_plan,
    sequence_actions,
    verify_plan,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _plan(seq_in: SequencerIn, *, plan_id: str = "plan-1"):
    rows = sequence_actions(seq_in)
    steps = compute_deadlines(rows, now=NOW)
    return build_plan(seq_in, steps, plan_id=plan_id)


# ---------------------------------------------------------------------------
# SequencerIn: closed enums only — "Riyadh" must not validate.
# ---------------------------------------------------------------------------


class TestSequencerInClosedEnums:
    def test_valid_construction(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert seq_in.country is Jurisdiction.SA

    def test_freetext_country_does_not_validate(self):
        with pytest.raises(Exception):
            SequencerIn(
                country="Riyadh",
                tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
                grievances=(Grievance.UNPAID_WAGES,),
            )

    def test_empty_grievances_does_not_validate(self):
        with pytest.raises(Exception):
            SequencerIn(
                country=Jurisdiction.SA,
                tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
                grievances=(),
            )

    def test_is_frozen(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        with pytest.raises(Exception):
            seq_in.country = Jurisdiction.QA


# ---------------------------------------------------------------------------
# jurisdiction_rules
# ---------------------------------------------------------------------------


def test_jurisdiction_rules_reports_active_and_held():
    from app.rules import JurisdictionStatus

    assert jurisdiction_rules(Jurisdiction.SA) is JurisdictionStatus.ACTIVE
    assert jurisdiction_rules(Jurisdiction.QA) is JurisdictionStatus.ACTIVE
    assert jurisdiction_rules(Jurisdiction.KW) is JurisdictionStatus.HELD
    assert jurisdiction_rules(Jurisdiction.AE) is JurisdictionStatus.HELD


# ---------------------------------------------------------------------------
# The 12-fixture pure suite: 6 SA, 4 QA, 2 KW/AE refusals.
# ---------------------------------------------------------------------------


class TestSaudiFixtures:
    """6 SA fixtures covering the tenure x grievance space that has rows."""

    def test_sa_wages_employed_reports_not_countdown(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.expires_at is None  # ReportedDeadline, never a countdown
        assert step.tier is SourceTier.TIER_2
        assert any(w.text and "90 days" in w.text for w in step.warnings)
        result = verify_plan(plan)
        assert result.ok, result.violations

    def test_sa_wages_left_employer_carries_huroob_warning(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        step = plan.steps[0]
        assert any("huroob" in w.text.lower() for w in step.warnings)
        assert verify_plan(plan).ok

    def test_sa_wages_departed_ships_confirm_first(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.DEPARTED_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        step = plan.steps[0]
        assert step.confirm_first_notes
        assert verify_plan(plan).ok

    def test_sa_passport_withheld_employed_never_asserts_deadline(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.PASSPORT_WITHHELD,),
        )
        plan = _plan(seq_in)
        assert plan.steps[0].expires_at is None
        assert verify_plan(plan).ok

    def test_sa_abuse_left_employer_never_routes_to_local_police(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
            grievances=(Grievance.PHYSICAL_ABUSE_OR_DANGER,),
        )
        plan = _plan(seq_in)
        step = plan.steps[0]
        assert "police" not in step.file_where.lower()
        assert any("police" in w.text.lower() for w in step.warnings)
        assert verify_plan(plan).ok

    def test_sa_exit_blocked_is_confirm_first_never_a_countdown(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.EXIT_BLOCKED,),
        )
        plan = _plan(seq_in)
        step = plan.steps[0]
        assert step.expires_at is None
        assert step.confirm_first_notes
        assert verify_plan(plan).ok

    def test_sa_multi_grievance_orders_abuse_before_wages(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES, Grievance.PHYSICAL_ABUSE_OR_DANGER),
        )
        plan = _plan(seq_in)
        grievance_order = [step.grievance for step in plan.steps]
        assert grievance_order.index(
            Grievance.PHYSICAL_ABUSE_OR_DANGER
        ) < grievance_order.index(Grievance.UNPAID_WAGES)


class TestQatarFixtures:
    """4 QA fixtures — ships at full strength, hard 1-year deadline."""

    def test_qa_wages_employed_hard_deadline(self):
        seq_in = SequencerIn(
            country=Jurisdiction.QA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        step = plan.steps[0]
        assert step.expires_at is not None
        assert step.tier is SourceTier.TIER_1
        assert verify_plan(plan).ok

    def test_qa_wages_departed_deadline_keeps_running(self):
        seq_in = SequencerIn(
            country=Jurisdiction.QA,
            tenure=TenureBucket.DEPARTED_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        assert plan.steps[0].expires_at is not None
        assert verify_plan(plan).ok

    def test_qa_passport_withheld_carries_fine_fact(self):
        seq_in = SequencerIn(
            country=Jurisdiction.QA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.PASSPORT_WITHHELD,),
        )
        plan = _plan(seq_in)
        step = plan.steps[0]
        assert any("25,000" in note or "QAR" in note for note in step.notes)
        assert verify_plan(plan).ok

    def test_qa_exit_blocked_asserts_right_to_leave(self):
        seq_in = SequencerIn(
            country=Jurisdiction.QA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.EXIT_BLOCKED,),
        )
        plan = _plan(seq_in)
        step = plan.steps[0]
        assert step.action_class is ActionClass.PROTECTIVE_REVERSIBLE
        assert verify_plan(plan).ok


class TestHeldRefusalFixtures:
    """2 KW/AE refusal fixtures — first-class, no sequence emitted."""

    def test_kw_raises_jurisdiction_held_and_emits_no_sequence(self):
        seq_in = SequencerIn(
            country=Jurisdiction.KW,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        with pytest.raises(JurisdictionHeldError):
            sequence_actions(seq_in)
        card = held_refusal_card(Jurisdiction.KW)
        assert card["type"] == "held_refusal"
        assert "Kuwait" in card["message"]
        assert "MWO" in card["message"]
        assert card["contacts"]

    def test_ae_raises_jurisdiction_held_and_emits_no_sequence(self):
        seq_in = SequencerIn(
            country=Jurisdiction.AE,
            tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
            grievances=(Grievance.PHYSICAL_ABUSE_OR_DANGER,),
        )
        with pytest.raises(JurisdictionHeldError):
            sequence_actions(seq_in)
        card = held_refusal_card(Jurisdiction.AE)
        assert card["type"] == "held_refusal"
        assert "UAE" in card["message"]
        assert "MWO" in card["message"]
        assert card["contacts"]


# ---------------------------------------------------------------------------
# Unresolved verify violations: no sequence emitted at the repair bound.
# ---------------------------------------------------------------------------


class TestVerifyFailureEmitsNoSequence:
    def test_missing_citation_url_is_a_violation(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        bad_citation = plan.steps[0].rule_citation.model_copy(update={"url": "not-a-url"})
        bad_step = plan.steps[0].model_copy(update={"rule_citation": bad_citation})
        tampered = plan.model_copy(update={"steps": (bad_step,)})
        result = verify_plan(tampered)
        assert not result.ok
        assert any("url" in v for v in result.violations)

    def test_empty_steps_is_a_violation(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = build_plan(seq_in, (), plan_id="empty-plan")
        result = verify_plan(plan)
        assert not result.ok
        assert any("no steps" in v for v in result.violations)

    def test_tier2_step_with_hard_deadline_is_a_violation(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        bad_step = plan.steps[0].model_copy(update={"expires_at": NOW.isoformat()})
        tampered = plan.model_copy(update={"steps": (bad_step,)})
        result = verify_plan(tampered)
        assert not result.ok
        assert any("countdown" in v for v in result.violations)

    def test_unverified_plan_is_never_published(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = build_plan(seq_in, (), plan_id="empty-plan")
        with pytest.raises(PlanNotVerifiedError):
            publish_plan(plan, cleared_hashes=frozenset())


# ---------------------------------------------------------------------------
# Structural test: publish_plan refuses a tampered plan hash.
# ---------------------------------------------------------------------------


class TestPublishPlanOutputGate:
    def test_publish_succeeds_when_hash_is_cleared(self):
        seq_in = SequencerIn(
            country=Jurisdiction.QA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        assert verify_plan(plan).ok
        cleared = frozenset({plan_hash(plan)})
        published = publish_plan(plan, cleared_hashes=cleared)
        assert published is plan

    def test_publish_refuses_a_hash_never_cleared(self):
        seq_in = SequencerIn(
            country=Jurisdiction.QA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        with pytest.raises(PlanNotVerifiedError):
            publish_plan(plan, cleared_hashes=frozenset({"not-this-hash"}))

    def test_publish_refuses_a_plan_tampered_after_verification(self):
        """The flagship structural test: clear a plan's hash, then mutate
        the plan (e.g. append a step) and try to publish that new object
        under the OLD cleared hash — it must refuse."""
        seq_in = SequencerIn(
            country=Jurisdiction.QA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        assert verify_plan(plan).ok
        cleared = frozenset({plan_hash(plan)})

        tampered_step = plan.steps[0].model_copy(update={"status": StepStatus.DONE})
        tampered_plan = plan.model_copy(update={"steps": (tampered_step,)})

        # Even though the tampered plan still verifies structurally, its
        # hash differs from the one that was cleared — publish must refuse.
        assert verify_plan(tampered_plan).ok
        with pytest.raises(PlanNotVerifiedError):
            publish_plan(tampered_plan, cleared_hashes=cleared)

    def test_publishing_the_original_after_tamper_check_still_works(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.PASSPORT_WITHHELD,),
        )
        plan = _plan(seq_in)
        cleared = frozenset({plan_hash(plan)})
        assert publish_plan(plan, cleared_hashes=cleared) is plan


# ---------------------------------------------------------------------------
# NoVerifiedPlanError: an empty rules_for cell must never invent a step.
# ---------------------------------------------------------------------------


class TestNoVerifiedPlanFallback:
    def test_sa_status_retaliation_outside_left_employer_has_no_rows(self):
        # docs/rules-corpus.md: SA STATUS_RETALIATION only has a row in
        # LEFT_EMPLOYER_IN_COUNTRY — DEPARTED_COUNTRY is an intentional gap.
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.DEPARTED_COUNTRY,
            grievances=(Grievance.STATUS_RETALIATION,),
        )
        with pytest.raises(NoVerifiedPlanError):
            sequence_actions(seq_in)


# ---------------------------------------------------------------------------
# input_hash: stable and content-sensitive.
# ---------------------------------------------------------------------------


class TestInputHash:
    def test_same_input_same_hash(self):
        a = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        b = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert input_hash(a) == input_hash(b)

    def test_different_input_different_hash(self):
        a = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        b = SequencerIn(
            country=Jurisdiction.QA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert input_hash(a) != input_hash(b)

    def test_plan_carries_its_input_hash(self):
        seq_in = SequencerIn(
            country=Jurisdiction.SA,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        plan = _plan(seq_in)
        assert plan.input_hash == input_hash(seq_in)
