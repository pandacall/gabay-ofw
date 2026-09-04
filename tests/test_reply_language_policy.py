"""Reply-language closed-set policy (issue #67, owner ruling 2026-09-03).

Supersedes "Tagalog in, Tagalog out; Taglish in, Taglish out; Cebuano in,
Cebuano out" with a closed set the agent must never step outside of:

* English input, unknown/turn-1, or any other detected language -> pure
  English (the DEFAULT, not a fallback for only Tagalog/Bisaya speakers).
* Filipino/Tagalog input ("tl") -> pure Filipino.
* Taglish input ("taglish") -> pure Filipino. Taglish stays a valid
  DETECTION value on ``CaseDelta.language`` (app/extraction.py) but the
  agent must never be instructed to PRODUCE it.
* Cebuano input ("ceb") -> pure Cebuano/Bisaya, same purity rule.

Two independent seams are checked here:

1. Prompt content — ``_dispatcher_instruction`` and ``_emergency_instruction``
   are plain functions of a readonly-context stub (no model call needed);
   we assert the literal instruction text never tells the model to
   produce Taglish, and does state the closed set above.
2. The acknowledgement mapping (``acknowledgement_for``) — deterministic
   app code, no model involved — maps a recorded "taglish" to the pure
   Filipino string, and an unrecorded/unknown language to English.
"""

from app.agent import (
    ACKNOWLEDGEMENTS,
    _dispatcher_instruction,
    _emergency_instruction,
    acknowledgement_for,
)
from app.emergency import open_latch
from app.state_keys import CASE, EMERGENCY_LATCH


class _FakeReadonlyContext:
    """The only surface ``_dispatcher_instruction``/``_emergency_instruction``
    touch: ``.state.get(key)``. A plain dict already satisfies that."""

    def __init__(self, state: dict):
        self.state = state


# Phrases that would mean an instruction tells the model to WRITE Taglish,
# as opposed to merely naming it as a detection value. Shared by both
# instruction suites below.
FORBIDDEN_TAGLISH_OUTPUT_PHRASES = [
    "reply in Taglish",
    "reply in taglish",
    "Taglish out",
    "write in Taglish",
    "output in Taglish",
]


def _assert_never_instructed_to_write_taglish(text: str) -> None:
    assert "Taglish in, Taglish out" not in text
    for phrase in FORBIDDEN_TAGLISH_OUTPUT_PHRASES:
        assert phrase not in text


class TestAcknowledgementMapping:
    def test_default_is_english(self):
        assert acknowledgement_for(None) == ACKNOWLEDGEMENTS["en"]

    def test_unrecognized_language_falls_back_to_english(self):
        assert acknowledgement_for("klingon") == ACKNOWLEDGEMENTS["en"]

    def test_tagalog_is_pure_filipino(self):
        assert acknowledgement_for("tl") == ACKNOWLEDGEMENTS["tl"]

    def test_cebuano_is_pure_cebuano(self):
        assert acknowledgement_for("ceb") == ACKNOWLEDGEMENTS["ceb"]

    def test_taglish_maps_to_the_filipino_acknowledgement(self):
        # The owner ruling: Taglish is detected, never produced — its
        # acknowledgement is the pure Filipino one, not a separate
        # Taglish-worded string.
        assert acknowledgement_for("taglish") == ACKNOWLEDGEMENTS["tl"]

    def test_no_taglish_worded_acknowledgement_exists(self):
        assert "taglish" not in ACKNOWLEDGEMENTS
        # The Filipino and Cebuano acknowledgements don't code-switch to
        # an English tail the way the old "taglish" entry used to.
        assert "one moment" not in ACKNOWLEDGEMENTS["tl"].lower()
        assert "one moment" not in ACKNOWLEDGEMENTS["ceb"].lower()


class TestDispatcherInstructionNeverProducesTaglish:
    def _instruction(self, *, case=None, **extra) -> str:
        return _dispatcher_instruction(
            _FakeReadonlyContext({CASE: case, **extra})
        )

    def test_default_turn_with_no_case_yet(self):
        text = self._instruction(case=None)
        assert "Taglish in, Taglish out" not in text
        assert "Tagalog in, Tagalog out" not in text
        assert "ENGLISH" in text
        assert "default" in text.lower()

    def test_no_instruction_tells_the_model_to_write_taglish(self):
        text = self._instruction(case={"language": "taglish"})
        # The word "Taglish" may appear (naming the detection value), but
        # nowhere as an instruction to reply/write/output in it.
        _assert_never_instructed_to_write_taglish(text)

    def test_taglish_recorded_language_instructs_pure_filipino(self):
        text = self._instruction(case={"language": "taglish"})
        assert '"language": "taglish"' in text  # the Case is shown verbatim
        assert "PURE Filipino" in text

    def test_states_english_default_for_unknown_or_english(self):
        text = self._instruction(case={"language": "en"})
        assert "ENGLISH" in text
        assert "default" in text.lower()

    def test_cebuano_purity_rule_present(self):
        text = self._instruction(case={"language": "ceb"})
        assert "Cebuano" in text
        assert "same purity rule" in text

    def test_resume_check_branch_also_never_writes_taglish(self):
        # The rare "long silence in the Emergency Conversation" branch
        # (issue #67 fix) must obey the same closed set as every other
        # DISPATCHER reply, not the old ambiguous "reply warmly in her
        # language". The latch is Conversation state now (ADR-0009).
        text = self._instruction(
            case={"language": "taglish"},
            **{
                EMERGENCY_LATCH: open_latch(now="2026-09-03T00:00:00+00:00"),
                "temp:resume_check": True,
            },
        )
        _assert_never_instructed_to_write_taglish(text)
        assert "PURE Filipino" in text
        assert "ENGLISH" in text


class TestEmergencyInstructionNeverProducesTaglish:
    def _instruction(self, *, case=None, **extra) -> str:
        return _emergency_instruction(
            _FakeReadonlyContext({CASE: case, **extra})
        )

    def test_no_instruction_tells_the_model_to_write_taglish(self):
        text = self._instruction(case={"language": "taglish"})
        _assert_never_instructed_to_write_taglish(text)

    def test_taglish_recorded_language_instructs_pure_filipino(self):
        text = self._instruction(case={"language": "taglish"})
        assert "PURE Filipino" in text
        assert "never produced" in text

    def test_english_default_present(self):
        text = self._instruction(case={"language": "en"})
        assert "ENGLISH" in text
        assert "default" in text.lower()
