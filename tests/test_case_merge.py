"""Merge-policy pure suite (PRD #34 testing decision: CI gate, no infra).

The most important assertions are what must NOT happen: no source may
clear a safety flag, and a user-confirmed value is never reverted.
"""

import copy

import pytest

from app.case import SAFETY_FLAGS, empty_case, merge_case

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
