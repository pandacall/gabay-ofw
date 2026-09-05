"""Pure tests for the conversation-replay seam (issue #72, ADR-0008).

Re-opening a Conversation loads its stored transcript and turns it back
into the same NDJSON line types ``/api/chat`` streams live, so the client
renders it through the identical ``handleChatLine`` path. This is the one
new seam PRD #69 sanctions.

Style matches ``tests/test_staleness.py`` / ``tests/test_case_merge.py``:
no model, no HTTP, no infrastructure — hand-built ADK ``Event`` lists in,
line dicts out. The load-bearing negative assertions:

* a past turn's deadline-bearing Plan card is NEVER replayed as an
  actionable card — it collapses to a single ``stale_plan_ref`` line, so
  ADR-0006's "expired deadline she acts on" is unreachable by scrollback
* the transient Progress Trail (ADR-0010) and the per-turn acknowledgement
  never appear in a replayed transcript
"""

from __future__ import annotations

from google.adk.events import Event
from google.genai import types

from app.emergency import EMERGENCY_OPENER_TRIGGER
from app.history import replay_conversation


def _user(text: str) -> Event:
    return Event(
        author="user",
        content=types.Content(role="user", parts=[types.Part(text=text)]),
    )


def _reply(text: str, *, author: str = "DISPATCHER") -> Event:
    return Event(
        author=author,
        content=types.Content(role="model", parts=[types.Part(text=text)]),
    )


def _tool_response(name: str, response: dict) -> Event:
    return Event(
        author=name,
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name=name, response=response
                    )
                )
            ],
        ),
    )


def test_a_bare_exchange_replays_as_user_then_reply_lines():
    lines = replay_conversation(
        [_user("they took my passport"), _reply("I hear you. Which country are you in?")]
    )

    assert lines == [
        {"type": "user", "text": "they took my passport"},
        {"type": "reply", "text": "I hear you. Which country are you in?"},
    ]


def test_the_emergency_opener_trigger_never_replays_as_her_message():
    # The proactive opener (spec 2026-09-06) is driven by a synthetic
    # user message; ADK persists it, but it is a stage direction, not
    # something she said, so it must not render as her bubble on re-open.
    lines = replay_conversation(
        [
            _user(EMERGENCY_OPENER_TRIGGER),
            _reply("I'm here with you. Do you want help thinking this "
                   "through, or did you just need the numbers?",
                   author="EMERGENCY"),
        ]
    )

    assert lines == [
        {
            "type": "reply",
            "text": "I'm here with you. Do you want help thinking this "
            "through, or did you just need the numbers?",
        },
    ]


def test_a_past_plan_card_collapses_to_a_single_stale_plan_ref_line():
    plan_card = {
        "type": "plan",
        "steps": [
            {"id": "s1", "status": "PENDING", "expires_at": "2026-01-01T00:00:00+00:00"}
        ],
    }
    lines = replay_conversation(
        [
            _user("what are my filing steps"),
            _tool_response("FILING_SEQUENCER", {"plan": plan_card}),
            _reply("Here is the order to file in."),
        ]
    )

    assert {"type": "stale_plan_ref"} in lines
    assert all(line["type"] != "card" for line in lines)


def test_clock_free_cards_replay_unchanged():
    safe_floor = {"type": "safe_floor", "country": "SA", "contacts": [{"label": "MWO"}]}
    lines = replay_conversation(
        [
            _user("who can help me"),
            _tool_response("safe_floor_card", {"card": safe_floor}),
            _reply("These offices can help."),
        ]
    )

    assert lines == [
        {"type": "user", "text": "who can help me"},
        {"type": "card", "card": safe_floor},
        {"type": "reply", "text": "These offices can help."},
    ]


def test_transient_scaffolding_and_foreign_authors_never_replay():
    # An empty before-agent-callback event (merge_case's state delta only),
    # a specialist's own text (only DISPATCHER/EMERGENCY are her reply),
    # and anything trail/ack-shaped contribute nothing to the transcript.
    lines = replay_conversation(
        [
            _user("hello"),
            Event(author="DISPATCHER", content=None),
            _reply("internal note", author="DEBUNKER"),
            _reply("Hello, I hear you."),
        ]
    )

    assert lines == [
        {"type": "user", "text": "hello"},
        {"type": "reply", "text": "Hello, I hear you."},
    ]


def test_a_search_corpus_response_replays_its_verdicts_line():
    verdicts = [{"claim": "c", "verdict": "FALSE", "rebuttal": "r", "source_name": "s"}]
    lines = replay_conversation(
        [
            _user("my agency said I can't leave"),
            _tool_response("search_corpus", {"verdicts": verdicts}),
            _reply("That is not correct."),
        ]
    )

    assert {"type": "verdicts", "verdicts": verdicts} in lines
