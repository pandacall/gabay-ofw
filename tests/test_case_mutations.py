"""Case mutation-replay pure suite (ADR-0008; issue #70): the safety fix
at the heart of this slice. ``apply_mutations`` is what the Firestore
transaction re-runs against the freshly-read stored Case instead of
trusting a merged blob computed before a concurrent write landed.
"""

from app.case import apply_mutations, empty_case, is_imminent_danger, merge_case

T1 = "2026-09-04T00:00:00+00:00"
T2 = "2026-09-04T00:05:00+00:00"
T3 = "2026-09-04T00:10:00+00:00"


def claims(**fields):
    return {name: {"value": value, "confidence": "high"} for name, value in fields.items()}


class TestEmergencyPressSurvivesInFlightCommit:
    """The concrete failure ADR-0008 exists to close: a DISPATCHER turn is
    in flight when she taps EMERGENCY. Replaying the button-press
    mutation against whatever the OTHER turn actually left behind must
    never lose the press, regardless of which mutation is recorded (and
    replayed) first."""

    def test_button_press_recorded_before_the_in_flight_merge_still_wins(self):
        # The button lands first; the in-flight DISPATCHER turn's
        # narrative merge (computed before the tap) is replayed after.
        mutations = [
            {"op": "press_emergency_button", "now": T1},
            {
                "op": "merge",
                "delta": {"claims": claims(country="Saudi Arabia")},
                "source": "extraction",
                "now": T2,
            },
        ]
        case = apply_mutations(None, mutations)
        assert is_imminent_danger(case) is True
        assert case["claims"]["country"]["value"] == "Saudi Arabia"

    def test_in_flight_merge_recorded_first_still_yields_active_after_the_press(self):
        # The reverse order: the stale in-flight turn's merge was recorded
        # (and would have been persisted) before the button press. Even
        # so, the press must still land — it is never silently erased by
        # replaying "the same stale blob" the way a whole-blob write
        # would.
        mutations = [
            {
                "op": "merge",
                "delta": {"claims": claims(country="Saudi Arabia")},
                "source": "extraction",
                "now": T1,
            },
            {"op": "press_emergency_button", "now": T2},
        ]
        case = apply_mutations(None, mutations)
        assert is_imminent_danger(case) is True
        assert case["claims"]["country"]["value"] == "Saudi Arabia"


class TestSafetyFlagSurvivesConcurrentCommit:
    def test_flag_from_one_writer_survives_a_later_writer_with_no_flags(self):
        # Writer A merged a safety flag; writer B's mutation (recorded
        # against an older Case, no flags) is replayed against the
        # ALREADY-flagged stored Case, per the transaction's freshly-read
        # value — never against writer B's own stale in-memory copy.
        stored = merge_case(None, {"safety_flags": ["PASSPORT_WITHHELD"]}, now=T1)
        writer_b_mutations = [
            {
                "op": "merge",
                "delta": {"claims": claims(employer_name="Al Rashid")},
                "source": "extraction",
                "now": T2,
            }
        ]
        replayed = apply_mutations(stored, writer_b_mutations)
        assert "PASSPORT_WITHHELD" in replayed["safety_flags"]
        assert replayed["claims"]["employer_name"]["value"] == "Al Rashid"


class TestUserCorrectionOutOfOrder:
    def test_replayed_late_still_wins_outright_and_resolves_conflict(self):
        # A prior extraction/document disagreement already left a
        # Conflict on the stored Case; her one-tap correction, recorded
        # earlier in wall-clock time but replayed AFTER, still resolves
        # it — merge_case's user-wins rule does not care about replay
        # order, only about the source.
        stored = merge_case(None, {"claims": claims(country="Saudi Arabia")}, now=T1)
        stored = merge_case(stored, {"claims": claims(country="Kuwait")}, source="document", now=T2)
        assert stored["claims"]["country"]["conflicts"]

        mutations = [
            {
                "op": "merge",
                "delta": {"claims": {"country": {"value": "Qatar", "confidence": "high"}}},
                "source": "user",
                "now": T3,
            }
        ]
        replayed = apply_mutations(stored, mutations)
        assert replayed["claims"]["country"]["value"] == "Qatar"
        assert replayed["claims"]["country"]["user_confirmed"] is True
        assert replayed["claims"]["country"]["conflicts"] == []


class TestUnknownMutationLeavesCaseIntact:
    def test_unknown_op_is_a_no_op(self):
        stored = merge_case(None, {"claims": claims(country="Qatar")}, now=T1)
        replayed = apply_mutations(stored, [{"op": "delete_everything", "now": T2}])
        assert replayed == stored

    def test_unknown_op_among_known_ones_does_not_block_the_rest(self):
        stored = empty_case()
        mutations = [
            {"op": "mystery", "now": T1},
            {"op": "press_emergency_button", "now": T2},
        ]
        replayed = apply_mutations(stored, mutations)
        assert is_imminent_danger(replayed) is True

    def test_non_dict_entries_are_ignored(self):
        stored = merge_case(None, {"claims": claims(country="Qatar")}, now=T1)
        replayed = apply_mutations(stored, ["a string", 42, None, ["nested"]])
        assert replayed == stored

    def test_missing_now_is_a_no_op(self):
        stored = empty_case()
        replayed = apply_mutations(stored, [{"op": "press_emergency_button"}])
        assert replayed == stored

    def test_merge_with_unrecognised_source_is_a_no_op(self):
        stored = empty_case()
        mutations = [
            {
                "op": "merge",
                "delta": {"claims": claims(country="Qatar")},
                "source": "model",
                "now": T1,
            }
        ]
        replayed = apply_mutations(stored, mutations)
        assert replayed == stored

    def test_merge_with_non_dict_delta_is_a_no_op(self):
        stored = empty_case()
        mutations = [{"op": "merge", "delta": "not-a-dict", "now": T1}]
        replayed = apply_mutations(stored, mutations)
        assert replayed == stored


class TestPurity:
    def test_input_case_not_mutated(self):
        import copy

        stored = merge_case(None, {"claims": claims(country="Qatar")}, now=T1)
        snapshot = copy.deepcopy(stored)
        mutations = [{"op": "press_emergency_button", "now": T2}]
        apply_mutations(stored, mutations)
        assert stored == snapshot

    def test_mutation_list_not_mutated(self):
        import copy

        mutations = [{"op": "press_emergency_button", "now": T1}]
        snapshot = copy.deepcopy(mutations)
        apply_mutations(None, mutations)
        assert mutations == snapshot

    def test_none_case_and_none_mutations_returns_none(self):
        assert apply_mutations(None, None) is None

    def test_empty_mutations_returns_same_case(self):
        stored = merge_case(None, {"claims": claims(country="Qatar")}, now=T1)
        assert apply_mutations(stored, []) == stored


class TestRecordEmergencyTurnMutation:
    def test_replays_last_turn_timestamp(self):
        stored = merge_case(None, {"safety_flags": ["THREAT_OF_HARM"]}, now=T1)
        mutations = [
            {"op": "record_emergency_turn", "now": T2, "resume_check_issued": False}
        ]
        replayed = apply_mutations(stored, mutations)
        assert replayed["emergency"]["last_turn_at"] == T2

    def test_resume_check_issued_flag_replays_too(self):
        stored = merge_case(None, {"safety_flags": ["THREAT_OF_HARM"]}, now=T1)
        mutations = [
            {"op": "record_emergency_turn", "now": T2, "resume_check_issued": True}
        ]
        replayed = apply_mutations(stored, mutations)
        assert replayed["emergency"]["resume_check_at"] == T2


class TestMarkSafeMutation:
    def test_replayed_late_clears_latch_but_never_the_flag(self):
        stored = merge_case(None, {"safety_flags": ["PHYSICAL_ASSAULT_ONGOING"]}, now=T1)
        assert is_imminent_danger(stored) is True
        replayed = apply_mutations(stored, [{"op": "mark_safe", "now": T2}])
        assert is_imminent_danger(replayed) is False
        assert "PHYSICAL_ASSAULT_ONGOING" in replayed["safety_flags"]
