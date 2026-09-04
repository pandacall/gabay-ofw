"""Conversation labels (issue #73, ADR-0008): claims-only, write-once, renameable.

A label names what she talked *about*, never what happened *to* her. It is
derived from Case claims by a fixed precedence and **never** from a Safety
Flag: a flag-derived label would put ``PHYSICAL_ASSAULT_ONGOING`` in a
sidebar her employer may see — the exact harm the neutral Emergency label
exists to prevent, reintroduced through a side door. Claims are safe
because they name a subject, not an allegation ("Passport and papers"
reads as admin).

Country and current location are excluded on purpose: nearly every first
message carries one, so they would swallow every row and the whole rail
would read as her country.

**Write-once.** A label that tracked the latest topic would rename the row
she remembers as "the passport one" into "Filing steps" the moment the
conversation wandered, and the rail's only job is helping her find things
again. It is written by code at the end of the first turn where an
identifiable claim exists and never re-derived. Because listing
Conversations deliberately loads no per-Conversation state, the label is
stored in the session document's own state rather than computed at list
time.

**Her own rename always wins**, permanently, over any derived label.

**The Emergency Conversation keeps its neutral date label forever** — a
session carrying the ``EMERGENCY_CONVERSATION`` marker is never labelled
from a topic, or the label deliberately made non-revealing becomes
revealing.
"""

from __future__ import annotations

from typing import Any

#: Session-scoped state key holding the resolved label. Its presence is
#: also the write-once latch: once set (by derivation or by her rename),
#: derivation never runs again for that Conversation.
CONVERSATION_LABEL = "conversation_label"

#: Session-scoped state key: ``"derived"`` (a precedence key the UI
#: localises) or ``"user"`` (the literal text she typed, shown verbatim).
CONVERSATION_LABEL_SOURCE = "conversation_label_source"

#: The session-scoped state keys a listing is allowed to carry so the
#: rail can render without loading a Conversation's transcript or the
#: per-user Case/Plan. Kept deliberately narrow (ADR-0008: "list_sessions
#: loads no state").
LISTING_STATE_KEYS: tuple[str, ...] = (
    CONVERSATION_LABEL,
    CONVERSATION_LABEL_SOURCE,
)

#: Session-scoped marker set by the Emergency Conversation (issue #74):
#: while present, no topic label is ever derived for this Conversation.
EMERGENCY_CONVERSATION = "emergency_conversation"

#: Fixed precedence — first match wins, so a turn touching several claims
#: is deterministic. Each entry is ``(label key, claim fields that fire
#: it)``. ``country`` and ``location_now`` appear nowhere: excluded by
#: design. Values are keys, not display strings; the UI localises them.
LABEL_PRECEDENCE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("passport", ("passport_location",)),
    ("wages", ("months_unpaid", "monthly_salary")),
    ("contract", ("contract_available",)),
    ("agency", ("agency_name",)),
    ("job", ("job_role", "tenure_months", "employer_name")),
)

#: Every label key the closed set may produce, for validation elsewhere.
LABEL_KEYS = frozenset(key for key, _ in LABEL_PRECEDENCE)


def _has_claim(claims: dict[str, Any], field: str) -> bool:
    claim = claims.get(field)
    return isinstance(claim, dict) and claim.get("value") not in (None, "")


def derive_label(case: dict[str, Any] | None) -> str | None:
    """The topic label key for a Case's claims, following the fixed
    precedence, or ``None`` when no identifiable claim is present (only
    then does the row keep the neutral date label). Never reads
    ``safety_flags`` — a conversation that contains only a safety
    disclosure derives ``None``.
    """
    claims = (case or {}).get("claims") or {}
    if not isinstance(claims, dict):
        return None
    for label, fields in LABEL_PRECEDENCE:
        if any(_has_claim(claims, field) for field in fields):
            return label
    return None


def label_state_delta(
    session_state: dict[str, Any] | None, case: dict[str, Any] | None
) -> dict[str, str] | None:
    """The session-state delta to persist this Conversation's derived
    label, or ``None`` when nothing should be written.

    ``None`` when: a label already exists (write-once — whether derived
    earlier or set by her rename), the Conversation is the Emergency
    Conversation, or no identifiable claim has been disclosed yet.
    """
    state = session_state or {}
    if state.get(CONVERSATION_LABEL):
        return None
    if state.get(EMERGENCY_CONVERSATION):
        return None
    label = derive_label(case)
    if label is None:
        return None
    return {
        CONVERSATION_LABEL: label,
        CONVERSATION_LABEL_SOURCE: "derived",
    }


def rename_state_delta(label: str) -> dict[str, str]:
    """The session-state delta for her own rename. Always wins: it
    overwrites any derived label and pins the source to ``"user"`` so a
    later turn's derivation is suppressed and the UI shows her text
    verbatim.
    """
    return {
        CONVERSATION_LABEL: label,
        CONVERSATION_LABEL_SOURCE: "user",
    }
