"""Conversation label derivation (issue #73): claims-only, write-once.

Pure-function tests for ``app.labels`` — the precedence, the exclusions,
the Safety-Flag firewall, the write-once latch, and rename winning.
"""

from __future__ import annotations

from app.labels import (
    CONVERSATION_LABEL,
    CONVERSATION_LABEL_SOURCE,
    CONVERSATION_TITLE_LLM_ATTEMPTED,
    EMERGENCY_CONVERSATION,
    derive_label,
    label_state_delta,
    llm_title_state_delta,
    rename_state_delta,
)


def _case(**claims: str) -> dict:
    return {
        "claims": {
            field: {"value": value, "confidence": "high"}
            for field, value in claims.items()
        },
        "safety_flags": {},
    }


class TestPrecedence:
    def test_passport_wins_over_everything(self):
        case = _case(
            passport_location="employer",
            months_unpaid="4",
            contract_available="no",
            agency_name="ABC",
            job_role="maid",
        )
        assert derive_label(case) == "passport"

    def test_wages_from_months_unpaid_or_salary(self):
        assert derive_label(_case(months_unpaid="4")) == "wages"
        assert derive_label(_case(monthly_salary="1200")) == "wages"

    def test_wages_beats_contract_agency_job(self):
        case = _case(months_unpaid="4", contract_available="no", agency_name="ABC", job_role="maid")
        assert derive_label(case) == "wages"

    def test_contract_then_agency_then_job(self):
        assert derive_label(_case(contract_available="no", agency_name="ABC")) == "contract"
        assert derive_label(_case(agency_name="ABC", job_role="maid")) == "agency"
        assert derive_label(_case(job_role="maid")) == "job"
        assert derive_label(_case(tenure_months="18")) == "job"
        assert derive_label(_case(employer_name="Al Rashid")) == "job"


class TestExclusionsAndFirewall:
    def test_country_and_location_never_produce_a_label(self):
        assert derive_label(_case(country="Saudi Arabia", location_now="Riyadh")) is None

    def test_safety_flag_only_conversation_has_no_label(self):
        case = {"claims": {}, "safety_flags": {"PHYSICAL_ASSAULT_ONGOING": {"source": "extraction"}}}
        assert derive_label(case) is None

    def test_empty_or_missing_case(self):
        assert derive_label(None) is None
        assert derive_label({}) is None
        assert derive_label({"claims": {}}) is None

    def test_blank_claim_value_does_not_fire(self):
        assert derive_label({"claims": {"job_role": {"value": ""}}}) is None


class TestWriteOnceLatch:
    def test_writes_derived_label_when_none_yet(self):
        delta = label_state_delta({}, _case(months_unpaid="4"))
        assert delta == {
            CONVERSATION_LABEL: "wages",
            CONVERSATION_LABEL_SOURCE: "derived",
        }

    def test_does_not_rewrite_an_existing_label(self):
        state = {CONVERSATION_LABEL: "passport", CONVERSATION_LABEL_SOURCE: "derived"}
        assert label_state_delta(state, _case(months_unpaid="4")) is None

    def test_does_not_overwrite_her_rename(self):
        state = {CONVERSATION_LABEL: "the passport one", CONVERSATION_LABEL_SOURCE: "user"}
        assert label_state_delta(state, _case(months_unpaid="4")) is None

    def test_no_write_without_an_identifiable_claim(self):
        assert label_state_delta({}, _case(country="Qatar")) is None

    def test_emergency_conversation_is_never_labelled(self):
        state = {EMERGENCY_CONVERSATION: True}
        assert label_state_delta(state, _case(passport_location="employer")) is None


class TestRename:
    def test_rename_pins_source_to_user(self):
        assert rename_state_delta("my word for it") == {
            CONVERSATION_LABEL: "my word for it",
            CONVERSATION_LABEL_SOURCE: "user",
        }


class TestLlmTitleStateDelta:
    """spec 2026-09-05-llm-conversation-titles: the one-time background
    LLM title attempt's write. Always marks attempted; only ever WRITES
    the label when one produced a safe title and none already exists —
    it never overwrites a claims-derived label or her rename, and (per
    that spec's explicit, accepted departure from the old invariant) it
    is NOT excluded for the Emergency Conversation.
    """

    def test_writes_label_and_marks_attempted_on_success(self):
        assert llm_title_state_delta({}, "Unpaid wages, several months") == {
            CONVERSATION_TITLE_LLM_ATTEMPTED: True,
            CONVERSATION_LABEL: "Unpaid wages, several months",
            CONVERSATION_LABEL_SOURCE: "llm",
        }

    def test_marks_attempted_only_when_title_is_none(self):
        assert llm_title_state_delta({}, None) == {
            CONVERSATION_TITLE_LLM_ATTEMPTED: True,
        }

    def test_never_overwrites_an_existing_derived_label(self):
        state = {CONVERSATION_LABEL: "wages", CONVERSATION_LABEL_SOURCE: "derived"}
        delta = llm_title_state_delta(state, "Passport concerns")
        assert delta == {CONVERSATION_TITLE_LLM_ATTEMPTED: True}

    def test_never_overwrites_her_rename(self):
        state = {CONVERSATION_LABEL: "the passport one", CONVERSATION_LABEL_SOURCE: "user"}
        delta = llm_title_state_delta(state, "Passport concerns")
        assert delta == {CONVERSATION_TITLE_LLM_ATTEMPTED: True}

    def test_not_excluded_for_the_emergency_conversation(self):
        # Deliberate departure from label_state_delta's EMERGENCY_CONVERSATION
        # exclusion — see the spec for the accepted risk.
        state = {EMERGENCY_CONVERSATION: True}
        assert llm_title_state_delta(state, "General inquiry") == {
            CONVERSATION_TITLE_LLM_ATTEMPTED: True,
            CONVERSATION_LABEL: "General inquiry",
            CONVERSATION_LABEL_SOURCE: "llm",
        }
