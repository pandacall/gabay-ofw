"""Named state keys for the Case and the Plan (ADR-0008).

One Case, and at most one live Plan, per user — never per Conversation
(ADK Session). Every reader and writer across the agent layer, the
tools, the guard, and the conversation spine MUST use these constants
rather than a bare string literal: a missed call site reads ``None``
forever and silently loses her facts.

``CASE`` / ``PLAN`` / ``PLAN_SEQ_IN`` / ``PLAN_ACTIVE`` are ``user:``-
prefixed — ADK's ``State`` (and ``FirestoreSessionService._split_state``)
already route a ``user:``-prefixed key to ``users/{uid}/adkUserState/
{appName}``, shared by every Conversation, rather than the per-session
document. The ``_RAW`` variants are the same keys with the prefix
stripped, matching what actually lives in that Firestore document (and
what ``_split_state`` yields in its ``"user"`` bucket).

``CASE_MUTATIONS`` / ``PLAN_MUTATIONS`` are ``temp:``-scoped: ADK strips
``temp:`` keys before persistence, so the raw mutation list this turn
recorded never lands in Firestore as a first-class field.
``FirestoreSessionService.append_event`` instead reads them back out of
the event's RAW state delta before that strip happens, and re-runs the
pure merge (``app.case.apply_mutations`` / ``app.plan_ops.apply_mutations``)
inside its own transaction, against the freshly-read stored Case/Plan —
never trusting a blob computed before a concurrent write.
"""

from __future__ import annotations

from google.adk.sessions.state import State

CASE_RAW = "case"
PLAN_RAW = "plan"
PLAN_SEQ_IN_RAW = "plan_seq_in"
PLAN_ACTIVE_RAW = "plan_active"

#: The Case: one per user (ADR-0008), never per Conversation.
CASE = State.USER_PREFIX + CASE_RAW

#: The Plan and its supporting fields: at most one LIVE Plan per user,
#: shared by every Conversation (ADR-0008 amendment).
PLAN = State.USER_PREFIX + PLAN_RAW
PLAN_SEQ_IN = State.USER_PREFIX + PLAN_SEQ_IN_RAW
PLAN_ACTIVE = State.USER_PREFIX + PLAN_ACTIVE_RAW

#: This turn's recorded Case mutations. See module docstring.
CASE_MUTATIONS = State.TEMP_PREFIX + "case_mutations"

#: This turn's recorded Plan mutations. See module docstring.
PLAN_MUTATIONS = State.TEMP_PREFIX + "plan_mutations"

# ---------------------------------------------------------------------------
# The Imminent Danger latch (ADR-0009, issue #74). It answers "is THIS
# Conversation the Emergency one" — Conversation state, never the Case. The
# Safety Flags that provoke it stay on her user-scoped Case; the latch
# rides with the Conversation and is gone the moment that Conversation is
# deleted. These are SESSION-scoped (no prefix): one per Conversation.
# ---------------------------------------------------------------------------

#: ``{"active": bool, "opened_at": iso|None, "marked_safe_at": iso|None}``.
#: ``active`` is written only at open (``create_session``, no race) and by
#: ``mark_safe`` — never by a turn — so a ``mark_safe`` racing an in-flight
#: Emergency turn can never be re-latched.
EMERGENCY_LATCH = "emergency_latch"

#: ``{"last_turn_at": iso|None, "resume_check_at": iso|None}`` — the
#: long-gap-resume bookkeeping (issue #41). A DISJOINT key from
#: ``EMERGENCY_LATCH`` on purpose: a turn writes only this, so it never
#: clobbers ``active``.
EMERGENCY_RESUME = "emergency_resume"

#: The Escalation Handoff carried into an Emergency Conversation at open
#: time and never after: ``{"country", "reason_category", "summary",
#: "source_session_id"}``. Never the source transcript.
ESCALATION_HANDOFF = "escalation_handoff"

#: A ``user:``-scoped pointer to the one live Emergency Conversation's
#: session id (ADR-0009: at most one live at a time). Set when one opens,
#: cleared by ``mark_safe`` and by deleting that Conversation. This is
#: what lets ``mark_safe`` keep working with no Conversation id from the
#: UI.
EMERGENCY_CONVERSATION_ID_RAW = "emergency_conversation_id"
EMERGENCY_CONVERSATION_ID = State.USER_PREFIX + EMERGENCY_CONVERSATION_ID_RAW
