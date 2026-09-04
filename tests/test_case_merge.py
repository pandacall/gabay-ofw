"""Merge-policy pure suite (PRD #34 testing decision: CI gate, no infra).

The most important assertions are what must NOT happen: no source may
clear a safety flag, and a user-confirmed value is never reverted.
"""

import copy

import pytest

from app.case import (
    ACUTE_SAFETY_FLAGS,
    SAFETY_FLAGS,
    SEQUENCER_FIELDS,
    empty_case,
    merge_case,
    unresolved_sequencer_conflict,
)

T1 = "2026-09-03T00:00:00+00:00"
T2 = "2026-09-03T00:05:00+00:00"


def claims(**fields):
    return {name: {"value": value, "confidence": "high"} for name, value in fields.items()}


class TestProvenance:
    def test_provenance_recorded_per_claim(self):
        case = merge_case(
            None,
            {"language": "taglish", "claims": claims(employer_name="Al Rashid", months_unpaid="3")},
            source="extraction",
            now=T1,
        )
        for field in ("employer_name", "months_unpaid"):
            claim = case["claims"][field]
            assert claim["source"] == "extraction"
            assert claim["confidence"] == "high"
            assert claim["at"] == T1
            assert claim["conflicts"] == []
        assert case["claims"]["employer_name"]["value"] == "Al Rashid"

    def test_newer_extraction_updates_unconfirmed_claim(self):
        case = merge_case(None, {"claims": claims(months_unpaid="2")}, now=T1)
        case = merge_case(case, {"claims": claims(months_unpaid="3")}, now=T2)
        assert case["claims"]["months_unpaid"]["value"] == "3"
        assert case["claims"]["months_unpaid"]["at"] == T2

    def test_unknown_source_rejected(self):
        with pytest.raises(ValueError):
            merge_case(None, {"claims": {}}, source="model", now=T1)


class TestUserConfirmedWins:
    def test_user_correction_sets_user_confirmed(self):
        case = merge_case(None, {"claims": claims(country="Saudi Arabia")}, source="user", now=T1)
        assert case["claims"]["country"]["user_confirmed"] is True
        assert case["claims"]["country"]["source"] == "user"

    def test_disagreeing_extraction_becomes_conflict_never_reverts(self):
        case = merge_case(None, {"claims": claims(country="Saudi Arabia")}, source="user", now=T1)
        case = merge_case(case, {"claims": claims(country="Kuwait")}, source="extraction", now=T2)
        claim = case["claims"]["country"]
        assert claim["value"] == "Saudi Arabia"
        assert claim["user_confirmed"] is True
        assert claim["conflicts"] == [
            {"value": "Kuwait", "source": "extraction", "confidence": "high", "at": T2}
        ]

    def test_disagreeing_document_becomes_conflict(self):
        case = merge_case(None, {"claims": claims(monthly_salary="1500")}, source="user", now=T1)
        case = merge_case(case, {"claims": claims(monthly_salary="1200")}, source="document", now=T2)
        assert case["claims"]["monthly_salary"]["value"] == "1500"
        assert case["claims"]["monthly_salary"]["conflicts"][0]["source"] == "document"

    def test_second_user_tap_resolves_earlier_conflict(self):
        # A conflict raised before her tap must not haunt the claim forever
        # (issue #44: a later correction wins outright and unblocks
        # sequencing, so any Conflict a prior turn raised is resolved, not
        # carried forward).
        case = merge_case(None, {"claims": claims(country="Saudi Arabia")}, source="user", now=T1)
        case = merge_case(case, {"claims": claims(country="Kuwait")}, source="extraction", now=T2)
        assert case["claims"]["country"]["conflicts"]
        case = merge_case(case, {"claims": claims(country="Qatar")}, source="user", now=T2)
        assert case["claims"]["country"]["value"] == "Qatar"
        assert case["claims"]["country"]["conflicts"] == []


class TestExtractionVsDocumentConflict:
    """Issue #44: extraction-vs-document disagreement persists BOTH values
    as a Conflict — the document is frequently the fraud (a substituted
    contract), so it never silently outranks her narrative, and her
    narrative never silently overwrites a document already on file either.
    """

    def test_document_disagreeing_with_narrative_becomes_conflict(self):
        # Demoable fixture (PRD #34): payslip says 14 months, she said 11.
        case = merge_case(None, {"claims": claims(months_unpaid="11")}, source="extraction", now=T1)
        case = merge_case(case, {"claims": claims(months_unpaid="14")}, source="document", now=T2)
        claim = case["claims"]["months_unpaid"]
        assert claim["value"] == "11"
        assert claim.get("user_confirmed") is not True
        assert claim["conflicts"] == [
            {"value": "14", "source": "document", "confidence": "high", "at": T2}
        ]

    def test_narrative_disagreeing_with_prior_document_becomes_conflict(self):
        # The reverse order: a document lands first, her later narrative
        # disagrees. Her narrative does not silently overwrite it either —
        # only her tap resolves the disagreement.
        case = merge_case(None, {"claims": claims(monthly_salary="1200")}, source="document", now=T1)
        case = merge_case(case, {"claims": claims(monthly_salary="1500")}, source="extraction", now=T2)
        claim = case["claims"]["monthly_salary"]
        assert claim["value"] == "1200"
        assert claim["conflicts"] == [
            {"value": "1500", "source": "extraction", "confidence": "high", "at": T2}
        ]

    def test_only_her_tap_resolves_an_extraction_document_conflict(self):
        case = merge_case(None, {"claims": claims(months_unpaid="11")}, now=T1)
        case = merge_case(case, {"claims": claims(months_unpaid="14")}, source="document", now=T2)
        case = merge_case(case, {"claims": claims(months_unpaid="11")}, source="user", now=T2)
        claim = case["claims"]["months_unpaid"]
        assert claim["value"] == "11"
        assert claim["user_confirmed"] is True
        assert claim["conflicts"] == []

    def test_same_source_refinement_still_overwrites_directly(self):
        # A same-source update (her narrative refining its own earlier
        # reading) is progressive refinement, not a cross-source
        # disagreement — it must keep overwriting directly.
        case = merge_case(None, {"claims": claims(months_unpaid="2")}, source="extraction", now=T1)
        case = merge_case(case, {"claims": claims(months_unpaid="3")}, source="extraction", now=T2)
        assert case["claims"]["months_unpaid"]["value"] == "3"
        assert case["claims"]["months_unpaid"]["conflicts"] == []

    def test_repeated_identical_disagreement_does_not_duplicate(self):
        # The same document re-processed (or the same fact re-extracted)
        # must update the existing Conflict entry, not pile up duplicates
        # the UI would render as separate tappable options.
        case = merge_case(None, {"claims": claims(country="Saudi Arabia")}, source="extraction", now=T1)
        case = merge_case(case, {"claims": claims(country="Kuwait")}, source="document", now=T2)
        case = merge_case(case, {"claims": claims(country="Kuwait")}, source="document", now="2026-09-03T00:10:00+00:00")
        conflicts = case["claims"]["country"]["conflicts"]
        assert len(conflicts) == 1
        assert conflicts[0]["at"] == "2026-09-03T00:10:00+00:00"


class TestUnresolvedSequencerConflict:
    """Issue #44: an unresolved Conflict on a SequencerIn-mapped field
    (country, tenure_months) blocks FILING_SEQUENCER; a Conflict on any
    other field is informational only and never blocks."""

    def test_no_case_or_empty_case_is_none(self):
        assert unresolved_sequencer_conflict(None) is None
        assert unresolved_sequencer_conflict(empty_case()) is None

    def test_uncontested_case_is_none(self):
        case = merge_case(None, {"claims": claims(country="Saudi Arabia")}, source="user", now=T1)
        assert unresolved_sequencer_conflict(case) is None

    def test_conflict_on_country_blocks(self):
        case = merge_case(None, {"claims": claims(country="Saudi Arabia")}, now=T1)
        case = merge_case(case, {"claims": claims(country="Kuwait")}, source="document", now=T2)
        assert unresolved_sequencer_conflict(case) == "country"

    def test_conflict_on_tenure_months_blocks(self):
        case = merge_case(None, {"claims": claims(tenure_months="6")}, now=T1)
        case = merge_case(case, {"claims": claims(tenure_months="18")}, source="document", now=T2)
        assert unresolved_sequencer_conflict(case) == "tenure_months"

    def test_conflict_on_non_sequencer_field_never_blocks(self):
        case = merge_case(None, {"claims": claims(employer_name="Al Rashid")}, now=T1)
        case = merge_case(case, {"claims": claims(employer_name="Al Fahad")}, source="document", now=T2)
        assert case["claims"]["employer_name"]["conflicts"]
        assert unresolved_sequencer_conflict(case) is None

    def test_resolving_the_conflict_unblocks(self):
        case = merge_case(None, {"claims": claims(country="Saudi Arabia")}, now=T1)
        case = merge_case(case, {"claims": claims(country="Kuwait")}, source="document", now=T2)
        assert unresolved_sequencer_conflict(case) == "country"
        case = merge_case(case, {"claims": claims(country="Saudi Arabia")}, source="user", now=T2)
        assert unresolved_sequencer_conflict(case) is None

    def test_sequencer_fields_matches_documented_set(self):
        assert SEQUENCER_FIELDS == {"country", "tenure_months"}


class TestSafetyFlagsAddOnly:
    def test_extraction_adds_flag_with_provenance(self):
        case = merge_case(None, {"safety_flags": ["PASSPORT_WITHHELD"]}, now=T1)
        assert case["safety_flags"]["PASSPORT_WITHHELD"] == {"source": "extraction", "at": T1}

    def test_delta_without_flags_never_clears(self):
        case = merge_case(None, {"safety_flags": ["CONFINED"]}, now=T1)
        case = merge_case(case, {"claims": claims(country="Qatar"), "safety_flags": []}, now=T2)
        assert "CONFINED" in case["safety_flags"]

    def test_document_can_never_clear_a_flag(self):
        # A doctored document claiming "all is well" carries no flags and a
        # disagreeing claim — the flag must survive it.
        case = merge_case(None, {"safety_flags": ["PHYSICAL_ASSAULT_PAST"]}, now=T1)
        case = merge_case(
            case, {"claims": claims(months_unpaid="0"), "safety_flags": []}, source="document", now=T2
        )
        assert "PHYSICAL_ASSAULT_PAST" in case["safety_flags"]

    def test_no_source_can_clear_any_flag(self):
        case = empty_case()
        for flag in sorted(SAFETY_FLAGS):
            case = merge_case(case, {"safety_flags": [flag]}, now=T1)
        for source in ("extraction", "document", "user"):
            case = merge_case(case, {"safety_flags": []}, source=source, now=T2)
        assert set(case["safety_flags"]) == SAFETY_FLAGS

    def test_readding_keeps_original_provenance(self):
        case = merge_case(None, {"safety_flags": ["CONFINED"]}, now=T1)
        case = merge_case(case, {"safety_flags": ["CONFINED"]}, source="document", now=T2)
        assert case["safety_flags"]["CONFINED"] == {"source": "extraction", "at": T1}

    def test_unknown_flag_ignored(self):
        case = merge_case(None, {"safety_flags": ["NOT_A_FLAG"]}, now=T1)
        assert case["safety_flags"] == {}


class TestDeterminism:
    def test_same_inputs_same_output_and_no_mutation(self):
        base = merge_case(None, {"claims": claims(country="Qatar")}, now=T1)
        delta = {"language": "tl", "claims": claims(months_unpaid="4"), "safety_flags": ["CONFINED"]}
        base_snapshot = copy.deepcopy(base)
        delta_snapshot = copy.deepcopy(delta)
        first = merge_case(base, delta, now=T2)
        second = merge_case(base, delta, now=T2)
        assert first == second
        assert base == base_snapshot
        assert delta == delta_snapshot

    def test_language_recorded_and_kept_without_new_reading(self):
        case = merge_case(None, {"language": "taglish", "claims": {}}, now=T1)
        assert case["language"] == "taglish"
        case = merge_case(case, {"claims": claims(country="Qatar")}, now=T2)
        assert case["language"] == "taglish"


class TestPendingEscalation:
    """ADR-0009 / issue #74: a NEW acute flag records a Pending Escalation
    on the Case — never a latch, never a transfer. The Imminent Danger
    latch lives on the Conversation now (``app.emergency``); see
    ``tests/test_emergency_latch.py``.
    """

    def test_acute_set_is_a_frozenset_in_code(self):
        assert isinstance(ACUTE_SAFETY_FLAGS, frozenset)
        assert ACUTE_SAFETY_FLAGS == {"PHYSICAL_ASSAULT_ONGOING", "THREAT_OF_HARM"}
        assert "PHYSICAL_ASSAULT_PAST" not in ACUTE_SAFETY_FLAGS
        assert ACUTE_SAFETY_FLAGS <= SAFETY_FLAGS

    def test_empty_case_has_no_pending_escalation_and_no_latch(self):
        case = empty_case()
        assert case["pending_escalation"] is None
        assert "emergency" not in case

    def test_new_acute_flag_records_a_pending_escalation(self):
        case = merge_case(None, {"safety_flags": ["PHYSICAL_ASSAULT_ONGOING"]}, now=T1)
        assert case["pending_escalation"] == {
            "flag": "PHYSICAL_ASSAULT_ONGOING",
            "at": T1,
        }
        # No latch anywhere on the Case.
        assert "emergency" not in case

    def test_threat_of_harm_also_records_one(self):
        case = merge_case(None, {"safety_flags": ["THREAT_OF_HARM"]}, now=T1)
        assert case["pending_escalation"]["flag"] == "THREAT_OF_HARM"

    def test_past_assault_records_nothing(self):
        case = merge_case(None, {"safety_flags": ["PHYSICAL_ASSAULT_PAST"]}, now=T1)
        assert case["pending_escalation"] is None

    def test_chronic_flags_alone_record_nothing(self):
        case = merge_case(None, {"safety_flags": ["CONFINED"]}, now=T1)
        case = merge_case(case, {"safety_flags": ["PASSPORT_WITHHELD"]}, now=T2)
        assert case["pending_escalation"] is None

    def test_a_second_different_acute_flag_updates_the_record(self):
        case = merge_case(None, {"safety_flags": ["PHYSICAL_ASSAULT_ONGOING"]}, now=T1)
        t3 = "2026-09-03T00:10:00+00:00"
        case = merge_case(case, {"safety_flags": ["THREAT_OF_HARM"]}, now=t3)
        assert case["pending_escalation"] == {"flag": "THREAT_OF_HARM", "at": t3}

    def test_re_adding_the_same_acute_flag_does_not_re_record(self):
        case = merge_case(None, {"safety_flags": ["THREAT_OF_HARM"]}, now=T1)
        case = merge_case(case, {"safety_flags": ["THREAT_OF_HARM"]}, now=T2)
        # Add-only: the flag is not new the second time, so the Pending
        # Escalation keeps its original ``at`` — a declined prompt can
        # never re-fire for the same hazard by construction.
        assert case["pending_escalation"] == {"flag": "THREAT_OF_HARM", "at": T1}

    def test_a_non_flag_turn_leaves_the_record_in_place(self):
        case = merge_case(None, {"safety_flags": ["THREAT_OF_HARM"]}, now=T1)
        case = merge_case(case, {"claims": claims(status="im_okay")}, now=T2)
        assert case["pending_escalation"] == {"flag": "THREAT_OF_HARM", "at": T1}

    def test_a_pre_migration_case_sheds_its_dead_emergency_dict(self):
        # ADR-0009: the latch left the Case. A Case persisted before the
        # migration carries a now-dead ``emergency`` dict; the next write
        # drops it.
        legacy = {
            "claims": {},
            "safety_flags": {},
            "language": None,
            "emergency": {"active": True, "button_pressed_at": T1},
        }
        merged = merge_case(legacy, {"claims": claims(country="Qatar")}, now=T2)
        assert "emergency" not in merged
        assert merged["claims"]["country"]["value"] == "Qatar"
