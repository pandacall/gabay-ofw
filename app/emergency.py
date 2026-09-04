"""The Imminent Danger latch and the Escalation Handoff (ADR-0009, issue #74).

The latch is **Conversation state, not a fact about her**. It answers one
question — "is *this* Conversation the Emergency one" — so it lives here,
not in ``app.case`` (which holds the Safety Flags that provoke it, on her
user-scoped Case). ``mark_safe`` clears the latch and never touches a
flag; deleting the Emergency Conversation takes the latch with it.

Set exactly two ways: the EMERGENCY button opening an Emergency
Conversation, or her confirming an Escalation Prompt. Cleared exactly one
way: ``mark_safe``. Never set by a disclosure alone — a mid-turn acute
disclosure records a **Pending Escalation** on the Case
(``app.case.merge_case``) and shows the Escalation Prompt; it transfers
nobody.

Storage (``app.state_keys``, all SESSION-scoped so each Conversation has
its own):

* ``EMERGENCY_LATCH``  — ``{"active", "opened_at", "marked_safe_at"}``.
  ``active`` is written only at open time (inside ``create_session``, no
  concurrency race) and by ``mark_safe``. A turn NEVER writes it.
* ``EMERGENCY_RESUME`` — ``{"last_turn_at", "resume_check_at"}``, the
  long-gap-resume bookkeeping (issue #41). A DISJOINT key so a turn's
  ``record_turn`` write can never clobber ``active``; a ``mark_safe``
  racing an in-flight Emergency turn is therefore never re-latched.
* ``ESCALATION_HANDOFF`` — written once, at open time. Country, reason
  category, a one-line summary in her language, the source Conversation's
  id. NEVER the source transcript.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.directory import resolve_case_country
from app.state_keys import EMERGENCY_LATCH, EMERGENCY_RESUME

#: How long a silence must be, while the latch is active, before the app
#: re-asks once instead of resuming her inside EMERGENCY (issue #41).
LONG_GAP_SECONDS = 30 * 60

#: Reason categories carried on the Escalation Handoff — a closed,
#: code-owned set, derived from her acute Safety Flags, never model text.
REASON_ASSAULT = "ASSAULT"
REASON_THREAT = "THREAT"
REASON_BUTTON = "BUTTON"
REASON_OTHER = "OTHER"

#: The one-line handoff summary for the EMERGENCY *button* path (no source
#: Conversation, no disclosure to summarise). Fixed per language, the same
#: closed set as ``app.agent.ACKNOWLEDGEMENTS`` — no model call.
BUTTON_SUMMARY: dict[str, str] = {
    "en": "She tapped the emergency button.",
    "tl": "Pinindot niya ang emergency button.",
    "ceb": "Iyang gipislit ang emergency button.",
}

#: The one-line handoff summary for the Escalation Prompt path, keyed by
#: reason category then language. Code-owned, derived from the acute flag —
#: never the transcript.
DISCLOSURE_SUMMARY: dict[str, dict[str, str]] = {
    REASON_ASSAULT: {
        "en": "She reported physical harm happening now, in conversation.",
        "tl": "Sinabi niya sa usapan na may pananakit na nangyayari ngayon.",
        "ceb": "Iyang gisulti sa panag-istorya nga naa pisikal nga kadaot karon.",
    },
    REASON_THREAT: {
        "en": "She reported being threatened with harm, in conversation.",
        "tl": "Sinabi niya sa usapan na pinagbabantaan siyang saktan.",
        "ceb": "Iyang gisulti sa panag-istorya nga gihulga siya og kadaot.",
    },
    REASON_OTHER: {
        "en": "She disclosed an acute safety concern in conversation.",
        "tl": "May malubhang alalahanin sa kaligtasan na sinabi niya sa usapan.",
        "ceb": "Naay grabe nga kabalaka sa kaluwasan nga iyang gisulti sa panag-istorya.",
    },
}

_FILIPINO_LANGUAGES = frozenset({"tl", "taglish"})


def _closed_language(language: str | None) -> str:
    return "tl" if language in _FILIPINO_LANGUAGES else (language or "en")


def empty_latch() -> dict[str, Any]:
    """A fresh, inactive latch: this Conversation is not the Emergency one."""
    return {"active": False, "opened_at": None, "marked_safe_at": None}


def empty_resume() -> dict[str, Any]:
    """Fresh long-gap-resume bookkeeping: no turn recorded yet."""
    return {"last_turn_at": None, "resume_check_at": None}


def is_emergency_conversation(state: Mapping[str, Any] | None) -> bool:
    """Whether ``state`` (a merged session/callback/tool state mapping)
    belongs to the live Emergency Conversation — the Imminent Danger
    latch, relocated from the Case (ADR-0009). Reads the latch, never the
    clock, never a flag.
    """
    if not state:
        return False
    latch = state.get(EMERGENCY_LATCH)
    if not isinstance(latch, Mapping):
        return False
    return bool(latch.get("active"))


def open_latch(*, now: str) -> dict[str, Any]:
    """The latch for a freshly opened Emergency Conversation."""
    return {"active": True, "opened_at": now, "marked_safe_at": None}


def clear_latch(latch: Mapping[str, Any] | None, *, now: str) -> dict[str, Any]:
    """``mark_safe``: flips the latch off, timestamped. Never touches a
    Safety Flag (this module cannot — flags live on the Case)."""
    merged = dict(copy.deepcopy(latch)) if latch else empty_latch()
    merged["active"] = False
    merged["marked_safe_at"] = now
    return merged


def record_turn(
    resume: Mapping[str, Any] | None,
    *,
    now: str,
    resume_check_issued: bool = False,
) -> dict[str, Any]:
    """Records this Emergency turn's timestamp so the next turn can detect
    a long gap. Writes ONLY the ``EMERGENCY_RESUME`` shape — never the
    latch — so it can never re-latch a Conversation ``mark_safe`` just
    cleared."""
    merged = dict(copy.deepcopy(resume)) if resume else empty_resume()
    merged["last_turn_at"] = now
    if resume_check_issued:
        merged["resume_check_at"] = now
    return merged


def _parse(at: str | None) -> datetime | None:
    if not at:
        return None
    try:
        return datetime.fromisoformat(at)
    except ValueError:
        return None


def needs_resume_check(
    latch: Mapping[str, Any] | None,
    resume: Mapping[str, Any] | None,
    *,
    now: str,
) -> bool:
    """Whether a long silence means DISPATCHER should re-ask once instead
    of silently resuming her inside EMERGENCY (issue #41). True only while
    the latch is active, a previous turn timestamp exists, the gap exceeds
    ``LONG_GAP_SECONDS``, and no resume check has already fired for this
    gap."""
    if not is_emergency_conversation({EMERGENCY_LATCH: latch}):
        return False
    resume = resume or {}
    last_turn = _parse(resume.get("last_turn_at"))
    current = _parse(now)
    if last_turn is None or current is None:
        return False
    if (current - last_turn).total_seconds() <= LONG_GAP_SECONDS:
        return False
    resume_check = _parse(resume.get("resume_check_at"))
    return resume_check is None or resume_check < last_turn


def reason_category_for(safety_flags: Any) -> str:
    """The Escalation Handoff reason category for a set/iterable of Safety
    Flag names — a closed, code-owned mapping, never model text. An acute
    ongoing assault outranks a threat; anything else acute is OTHER."""
    flags = set(safety_flags or [])
    if "PHYSICAL_ASSAULT_ONGOING" in flags:
        return REASON_ASSAULT
    if "THREAT_OF_HARM" in flags:
        return REASON_THREAT
    return REASON_OTHER


def button_summary(language: str | None) -> str:
    """The fixed handoff summary for the EMERGENCY button path."""
    return BUTTON_SUMMARY.get(_closed_language(language), BUTTON_SUMMARY["en"])


def disclosure_summary(reason_category: str, language: str | None) -> str:
    """The fixed handoff summary for the Escalation Prompt path — derived
    from the reason category only, never the transcript."""
    table = DISCLOSURE_SUMMARY.get(reason_category, DISCLOSURE_SUMMARY[REASON_OTHER])
    return table.get(_closed_language(language), table["en"])


def build_handoff(
    *,
    case: Mapping[str, Any] | None,
    source_session_id: str | None,
    reason_category: str,
    summary: str,
) -> dict[str, Any]:
    """The minimal object carried into an Emergency Conversation at open
    time (ADR-0009): country, reason category, a one-line summary in her
    language, the source Conversation's id. Never the transcript."""
    return {
        "country": resolve_case_country(
            dict(case) if isinstance(case, Mapping) else None
        ).value,
        "reason_category": reason_category,
        "summary": summary,
        "source_session_id": source_session_id,
    }
