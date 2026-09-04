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
