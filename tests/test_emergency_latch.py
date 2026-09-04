"""The Imminent Danger latch, pure suite (ADR-0009, issue #74).

The latch relocated from the Case to the Conversation: it answers "is
*this* Conversation the Emergency one". Set only at open time or by a
confirmed Escalation Prompt; cleared only by ``mark_safe``. The long-gap
resume bookkeeping (issue #41) rides on a DISJOINT key so a turn can never
re-latch a Conversation ``mark_safe`` just cleared.
"""

import copy
import inspect

from app.emergency import (
    LONG_GAP_SECONDS,
    REASON_ASSAULT,
    REASON_OTHER,
    REASON_THREAT,
    build_handoff,
    button_summary,
    clear_latch,
    disclosure_summary,
    empty_latch,
    empty_resume,
    is_emergency_conversation,
    needs_resume_check,
    open_latch,
    reason_category_for,
    record_turn,
)
from app.state_keys import EMERGENCY_LATCH, EMERGENCY_RESUME

T1 = "2026-09-03T00:00:00+00:00"
T2 = "2026-09-03T00:05:00+00:00"
T_LATER = "2026-09-03T01:00:00+00:00"  # 1h later: past the gap
T_AFTER = "2026-09-03T01:05:00+00:00"
T_EVEN_LATER = "2026-09-03T02:00:00+00:00"


class TestIsEmergencyConversation:
    def test_no_state_or_no_latch_is_false(self):
        assert is_emergency_conversation(None) is False
        assert is_emergency_conversation({}) is False
        assert is_emergency_conversation({EMERGENCY_LATCH: empty_latch()}) is False

    def test_open_latch_makes_it_true(self):
        state = {EMERGENCY_LATCH: open_latch(now=T1)}
        assert is_emergency_conversation(state) is True

    def test_reads_the_latch_never_a_flag_or_the_clock(self):
        # No "now"/elapsed-time parameter — a pure latch read.
        params = inspect.signature(is_emergency_conversation).parameters
        assert list(params) == ["state"]

    def test_a_non_dict_latch_is_false(self):
        assert is_emergency_conversation({EMERGENCY_LATCH: "yes"}) is False


class TestOpenAndClear:
    def test_open_latch_is_active_and_timestamped(self):
        latch = open_latch(now=T1)
        assert latch["active"] is True
        assert latch["opened_at"] == T1
        assert latch["marked_safe_at"] is None

    def test_clear_latch_flips_active_off_timestamped(self):
        latch = open_latch(now=T1)
        cleared = clear_latch(latch, now=T2)
        assert cleared["active"] is False
        assert cleared["marked_safe_at"] == T2
        assert cleared["opened_at"] == T1  # audit trail preserved

    def test_clear_latch_does_not_mutate_input(self):
        latch = open_latch(now=T1)
        snapshot = copy.deepcopy(latch)
        clear_latch(latch, now=T2)
        assert latch == snapshot

    def test_clear_latch_tolerates_missing_latch(self):
        assert clear_latch(None, now=T2)["active"] is False


class TestLongGapResume:
    """Issue #41: a long silence while the latch is active re-asks once."""

    def _latch(self):
        return open_latch(now=T1)

    def test_no_check_when_latch_inactive(self):
        resume = record_turn(empty_resume(), now=T1)
        assert needs_resume_check(empty_latch(), resume, now=T_LATER) is False

    def test_short_gap_does_not_trigger(self):
        resume = record_turn(empty_resume(), now=T1)
        assert needs_resume_check(self._latch(), resume, now=T2) is False

    def test_long_gap_triggers_exactly_once(self):
        resume = record_turn(empty_resume(), now=T1)
        assert needs_resume_check(self._latch(), resume, now=T_LATER) is True
        resume = record_turn(resume, now=T_LATER, resume_check_issued=True)
        assert needs_resume_check(self._latch(), resume, now=T_LATER) is False

    def test_fires_again_after_a_second_long_gap(self):
        resume = record_turn(empty_resume(), now=T1)
        assert needs_resume_check(self._latch(), resume, now=T_LATER) is True
        resume = record_turn(resume, now=T_LATER, resume_check_issued=True)
        resume = record_turn(resume, now=T_AFTER)
        assert needs_resume_check(self._latch(), resume, now=T_EVEN_LATER) is True

    def test_record_turn_never_touches_the_latch_key(self):
        # The disjoint-key guarantee: record_turn returns ONLY the resume
        # shape, so a mark_safe racing an in-flight Emergency turn is
        # never re-latched (ADR-0009).
        out = record_turn(empty_resume(), now=T1)
        assert set(out) == {"last_turn_at", "resume_check_at"}
        assert "active" not in out

    def test_long_gap_seconds_is_thirty_minutes(self):
        assert LONG_GAP_SECONDS == 30 * 60


class TestReasonCategory:
    def test_ongoing_assault_outranks_threat(self):
        assert reason_category_for(
            {"PHYSICAL_ASSAULT_ONGOING", "THREAT_OF_HARM"}
        ) == REASON_ASSAULT

    def test_threat_alone(self):
        assert reason_category_for({"THREAT_OF_HARM"}) == REASON_THREAT

    def test_no_acute_flag_is_other(self):
        assert reason_category_for({"PASSPORT_WITHHELD"}) == REASON_OTHER
        assert reason_category_for([]) == REASON_OTHER


class TestHandoff:
    def test_carries_country_reason_summary_and_source_never_transcript(self):
        case = {"claims": {"country": {"value": "Saudi Arabia"}}, "safety_flags": {}}
        handoff = build_handoff(
            case=case,
            source_session_id="src-123",
            reason_category=REASON_THREAT,
            summary=disclosure_summary(REASON_THREAT, "tl"),
        )
        assert handoff == {
            "country": "SA",
            "reason_category": REASON_THREAT,
            "summary": disclosure_summary(REASON_THREAT, "tl"),
            "source_session_id": "src-123",
        }
        # Nothing transcript-shaped is anywhere in it.
        assert set(handoff) == {
            "country",
            "reason_category",
            "summary",
            "source_session_id",
        }

    def test_button_path_has_no_source_and_a_fixed_summary(self):
        handoff = build_handoff(
            case=None,
            source_session_id=None,
            reason_category="BUTTON",
            summary=button_summary("en"),
        )
        assert handoff["source_session_id"] is None
        assert handoff["summary"] == button_summary("en")

    def test_summaries_follow_the_closed_language_set(self):
        assert button_summary("ceb") != button_summary("en")
        # Taglish folds to pure Filipino, never a mixed string.
        assert button_summary("taglish") == button_summary("tl")
        assert disclosure_summary(REASON_ASSAULT, "taglish") == disclosure_summary(
            REASON_ASSAULT, "tl"
        )
