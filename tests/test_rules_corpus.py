"""Pure-function validation suite for the rules corpus (issue #36).

CI-gate style per PRD #34: seconds-fast, no infrastructure, no API key.
The most important assertions are what must NOT happen: no Tier-2 hard
dates, no rows for HELD jurisdictions, no local-police venue, no invented
enum granularity.
"""

import re

import pytest
from pydantic import ValidationError

from app.rules import (
    JURISDICTION_STATUS,
    RULES_CORPUS,
    ActionClass,
    Citation,
    FilingTiming,
    Grievance,
    HardDeadline,
    Jurisdiction,
    JurisdictionStatus,
    ReportedDeadline,
    RuleRow,
    SourceTier,
    TenureBucket,
    jurisdiction_status,
    rules_for,
)

HEDGES = ("reportedly", "may be", "might", "possibly", "allegedly", "perhaps")

SA_ROWS = [r for r in RULES_CORPUS if r.jurisdiction is Jurisdiction.SA]
QA_ROWS = [r for r in RULES_CORPUS if r.jurisdiction is Jurisdiction.QA]


def _content_key(row: RuleRow) -> tuple:
    """Row content minus identity fields, for branch-distinction checks."""
    return (
        row.file_where,
        row.filing_timing,
        row.action_class,
        None if row.deadline is None else row.deadline.model_dump_json(),
        tuple(w.text for w in row.warnings),
        row.confirm_first_notes,
        row.notes,
    )


# ---------------------------------------------------------------------------
# Acceptance: rows exist as reviewable data with citation + tier per row
# ---------------------------------------------------------------------------


def test_sa_and_qa_rows_exist():
    assert SA_ROWS and QA_ROWS


def test_every_row_has_citation_and_tier():
    for row in RULES_CORPUS:
        assert row.citation.source_name.strip()
        assert row.citation.reference.strip()
        assert row.citation.url.startswith("http"), row.row_id
        assert row.tier in (SourceTier.TIER_1, SourceTier.TIER_2)
        for warning in row.warnings:
            assert warning.citation.url.startswith("http"), row.row_id


def test_row_ids_unique():
    ids = [r.row_id for r in RULES_CORPUS]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Acceptance: KW/AE explicitly HELD with no rows
# ---------------------------------------------------------------------------


def test_kw_ae_held_with_no_rows():
    for held in (Jurisdiction.KW, Jurisdiction.AE):
        assert jurisdiction_status(held) is JurisdictionStatus.HELD
        assert not [r for r in RULES_CORPUS if r.jurisdiction is held]
        for grievance in Grievance:
            for tenure in TenureBucket:
                assert rules_for(held, grievance, tenure) == ()


def test_every_jurisdiction_has_explicit_status():
    assert set(JURISDICTION_STATUS) == set(Jurisdiction)


# ---------------------------------------------------------------------------
# Acceptance: tier bounds are structural (ADR-0005)
# ---------------------------------------------------------------------------


def _tier2_citation() -> Citation:
    return Citation(
        source_name="s", reference="r", url="https://example.org", tier=SourceTier.TIER_2
    )


def test_schema_rejects_tier2_row_with_hard_deadline():
    with pytest.raises(ValidationError, match="hard deadline"):
        RuleRow(
            row_id="x",
            jurisdiction=Jurisdiction.SA,
            grievance=Grievance.UNPAID_WAGES,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            file_where="somewhere",
            filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
            action_class=ActionClass.PROTECTIVE_REVERSIBLE,
            deadline=HardDeadline(duration_days=30, starts_from="event"),
            citation=_tier2_citation(),
            tier=SourceTier.TIER_2,
        )


def test_schema_rejects_tier2_row_directing_irreversible_action():
    with pytest.raises(ValidationError, match="irreversible"):
        RuleRow(
            row_id="x",
            jurisdiction=Jurisdiction.SA,
            grievance=Grievance.UNPAID_WAGES,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            file_where="somewhere",
            filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
            action_class=ActionClass.IRREVERSIBLE,
            citation=_tier2_citation(),
            tier=SourceTier.TIER_2,
        )


def test_schema_rejects_tier_upgrade_of_weaker_citation():
    with pytest.raises(ValidationError, match="never.*upgrade"):
        RuleRow(
            row_id="x",
            jurisdiction=Jurisdiction.QA,
            grievance=Grievance.UNPAID_WAGES,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            file_where="somewhere",
            filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
            action_class=ActionClass.PROTECTIVE_REVERSIBLE,
            citation=_tier2_citation(),
            tier=SourceTier.TIER_1,
        )


# ---------------------------------------------------------------------------
# Acceptance: Saudi Tier-2 constraints applied
# ---------------------------------------------------------------------------


def test_all_sa_rows_ship_at_tier2():
    for row in SA_ROWS:
        assert row.tier is SourceTier.TIER_2, row.row_id


def test_no_sa_row_asserts_hard_date_or_irreversible_action():
    for row in SA_ROWS:
        assert not isinstance(row.deadline, HardDeadline), row.row_id
        assert row.action_class is ActionClass.PROTECTIVE_REVERSIBLE, row.row_id


def test_sa_deadlines_are_reported_not_relied_upon():
    dated = [r for r in SA_ROWS if r.deadline is not None]
    assert dated, "SA money rows must still report the limitation"
    for row in dated:
        assert isinstance(row.deadline, ReportedDeadline), row.row_id
        assert "MWO" in row.deadline.confirm_with, row.row_id


def test_sa_exit_visa_timing_is_confirm_first_never_a_countdown():
    exit_rows = [r for r in SA_ROWS if r.grievance is Grievance.EXIT_BLOCKED]
    assert exit_rows
    for row in exit_rows:
        assert row.deadline is None, row.row_id
        assert row.confirm_first_notes, row.row_id
        joined = " ".join(row.confirm_first_notes)
        assert "MWO" in joined, row.row_id
        # A countdown is a number of days/hours/weeks; confirm-first
        # notes must not contain one.
        assert not re.search(r"\d+\s*(day|hour|week|month)", joined), row.row_id


def test_sa_90_day_warning_ships_unhedged_on_every_wage_row():
    wage_rows = [r for r in SA_ROWS if r.grievance is Grievance.UNPAID_WAGES]
    assert wage_rows
    for row in wage_rows:
        ninety = [w for w in row.warnings if "90 days" in w.text]
        assert ninety, f"{row.row_id}: missing the 90-day non-withdrawal warning"
        for warning in ninety:
            lowered = warning.text.lower()
            for hedge in HEDGES:
                assert hedge not in lowered, (
                    f"{row.row_id}: 90-day warning is hedged ({hedge!r})"
                )
            assert warning.citation.url.startswith("http")


# ---------------------------------------------------------------------------
# Qatar ships at full strength (Tier-1)
# ---------------------------------------------------------------------------


def test_all_qa_rows_ship_at_tier1():
    for row in QA_ROWS:
        assert row.tier is SourceTier.TIER_1, row.row_id


def test_qa_money_claims_carry_the_hard_one_year_deadline():
    wage_rows = [r for r in QA_ROWS if r.grievance is Grievance.UNPAID_WAGES]
    assert wage_rows
    for row in wage_rows:
        assert isinstance(row.deadline, HardDeadline), row.row_id
        assert row.deadline.duration_days == 365, row.row_id


# ---------------------------------------------------------------------------
# Acceptance: enums derived from rows, never invented granularity
# ---------------------------------------------------------------------------


def test_every_grievance_value_is_used_by_a_row():
    used = {r.grievance for r in RULES_CORPUS}
    assert used == set(Grievance)


def test_every_tenure_bucket_is_used_by_a_row():
    used = {r.tenure for r in RULES_CORPUS}
    assert used == set(TenureBucket)


def test_tenure_buckets_actually_distinguish_rows():
    """For each pair of buckets there is a (jurisdiction, grievance) whose
    rows differ across the buckets — otherwise the bucket is invented."""
    buckets = list(TenureBucket)
    for i, a in enumerate(buckets):
        for b in buckets[i + 1 :]:
            distinguishing = False
            for jurisdiction in (Jurisdiction.SA, Jurisdiction.QA):
                for grievance in Grievance:
                    rows_a = rules_for(jurisdiction, grievance, a)
                    rows_b = rules_for(jurisdiction, grievance, b)
                    if not rows_a or not rows_b:
                        continue
                    if {_content_key(r) for r in rows_a} != {
                        _content_key(r) for r in rows_b
                    }:
                        distinguishing = True
            assert distinguishing, f"buckets {a.value} and {b.value} never differ"


def test_grievance_values_actually_distinguish_rows():
    """No two grievance values give identical guidance in every cell they
    share — otherwise one of them is invented granularity."""
    values = list(Grievance)
    for i, a in enumerate(values):
        for b in values[i + 1 :]:
            shared_cells = 0
            differing_cells = 0
            for jurisdiction in (Jurisdiction.SA, Jurisdiction.QA):
                for tenure in TenureBucket:
                    rows_a = rules_for(jurisdiction, a, tenure)
                    rows_b = rules_for(jurisdiction, b, tenure)
                    if not rows_a or not rows_b:
                        continue
                    shared_cells += 1
                    if {_content_key(r) for r in rows_a} != {
                        _content_key(r) for r in rows_b
                    }:
                        differing_cells += 1
            assert shared_cells > 0, f"{a.value} and {b.value} never co-occur"
            assert differing_cells > 0, (
                f"grievances {a.value} and {b.value} give identical guidance "
                "everywhere they co-occur — collapse them"
            )


# ---------------------------------------------------------------------------
# ROUTING_GUARD invariant: no row files at the local police
# ---------------------------------------------------------------------------


def test_no_row_names_police_as_a_filing_venue():
    for row in RULES_CORPUS:
        assert "police" not in row.file_where.lower(), row.row_id


# ---------------------------------------------------------------------------
# Consumable without transformation
# ---------------------------------------------------------------------------


def test_rules_for_returns_ready_rows():
    rows = rules_for(
        Jurisdiction.QA, Grievance.UNPAID_WAGES, TenureBucket.EMPLOYED_IN_COUNTRY
    )
    assert rows
    row = rows[0]
    # Everything sequence_actions/verify_plan need, on the object itself.
    assert row.file_where
    assert row.filing_timing is FilingTiming.BEFORE_LEAVING_COUNTRY
    assert isinstance(row.deadline, HardDeadline)
    assert row.citation.url.startswith("http")
    assert row.tier is SourceTier.TIER_1


def test_rows_are_immutable():
    row = RULES_CORPUS[0]
    with pytest.raises(ValidationError):
        row.file_where = "somewhere else"
