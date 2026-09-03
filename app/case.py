"""The Case: structured facts merged deterministically from CaseDeltas.

``merge_case`` is a pure function (PRD #34, merge policy): provenance is
recorded per claim, user-confirmed values are never reverted by a later
extraction (a disagreement becomes a Conflict on the claim), and safety
flags sit outside precedence entirely — a delta may ADD a flag and may
NEVER clear one. There is deliberately no code path that removes a flag:
only an authenticated UI action clears (out of scope for this slice).

Everything stored in the Case is a JSON-serialisable plain dict so it can
live in ADK session state and in Firestore unchanged.

Imminent Danger predicate (issue #41, PRD #34): acuteness is a property of
the safety-flag enum member itself — ``ACUTE_SAFETY_FLAGS`` is a frozenset
in code, never a side table. ``PHYSICAL_ASSAULT_ONGOING`` and
``THREAT_OF_HARM`` are acute; ``PHYSICAL_ASSAULT_PAST`` is not.
``CONFINED`` and ``PASSPORT_WITHHELD`` are chronic baseline (near-universal
per Amnesty) and are never acute on their own.

The predicate itself (``case["emergency"]["active"]``) is a separate,
mutable latch — NOT a live recomputation of "flag in acute set" — because
``mark_safe`` must be able to clear it without touching the (add-only,
never-cleared) safety flags. It is set True the moment a new acute flag is
merged in or the EMERGENCY button is pressed, and it is the ONLY thing
``mark_safe`` clears. It never expires by clock: nothing here reads a
timestamp to decide whether it is still true.

Long-gap resume (issue #41): if the predicate is active but a long silence
has passed since the last turn, the app re-asks ONCE — a plain DISPATCHER
check-in — instead of silently resuming her inside EMERGENCY as if nothing
happened. This is orthogonal to the predicate itself: it never clears
``active`` and never touches the flag; it only decides, for exactly one
turn, whether DISPATCHER should check in before transferring again.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

#: How long a silence must be, while the predicate is active, before the
#: app re-asks once instead of resuming inside EMERGENCY.
LONG_GAP_SECONDS = 30 * 60

# Safety flag enum. The flag vocabulary is fixed here so extraction is
# validated against a closed set.
SAFETY_FLAGS = frozenset(
    {
        "PHYSICAL_ASSAULT_ONGOING",
        "PHYSICAL_ASSAULT_PAST",
        "THREAT_OF_HARM",
        "CONFINED",
        "PASSPORT_WITHHELD",
    }
)

#: Acute-class flags trip the Imminent Danger predicate on their own.
#: Chronic flags (CONFINED, PASSPORT_WITHHELD) are the Gulf baseline and
#: are acute only in combination with an active threat or stated
#: escalation — i.e. only when THREAT_OF_HARM or PHYSICAL_ASSAULT_ONGOING
#: is *also* present, which this frozenset membership check already
#: covers without a side table.
ACUTE_SAFETY_FLAGS = frozenset({"PHYSICAL_ASSAULT_ONGOING", "THREAT_OF_HARM"})

# Provenance sources. Only these may author a claim; none of them may clear
# a safety flag. "debunker" is DEBUNKER's verdict write (issue #47): a
# plan-relevant FALSE lands on the Case with provenance so a Plan resting
# on the belief goes stale via the input-hash mechanism (issue #43).
CLAIM_SOURCES = frozenset({"extraction", "document", "user", "debunker"})


def _empty_emergency() -> dict[str, Any]:
    """Fresh Imminent Danger predicate state: no trigger, no clearing."""
    return {
        "active": False,
        "button_pressed_at": None,
        "marked_safe_at": None,
        "flag_triggered_at": None,
        "last_turn_at": None,
        "resume_check_at": None,
    }


def empty_case() -> dict[str, Any]:
    """A fresh Case: no claims, no flags, no recorded language."""
    return {
        "claims": {},
        "safety_flags": {},
        "language": None,
        "emergency": _empty_emergency(),
    }


def is_imminent_danger(case: dict[str, Any] | None) -> bool:
    """The Imminent Danger predicate: reads the latch, never the clock.

    This is deliberately NOT "an acute flag is present" recomputed live —
    that would make ``mark_safe`` unable to ever clear the predicate once
    an acute flag lands, since flags are add-only. The latch in
    ``case["emergency"]["active"]`` is what ``merge_case`` sets on a new
    acute flag, what ``press_emergency_button`` sets on a button tap, and
    the only thing ``mark_safe`` clears.
    """
    if not case:
        return False
    emergency = case.get("emergency")
    if not isinstance(emergency, dict):
        return False
    return bool(emergency.get("active"))


def press_emergency_button(
    case: dict[str, Any] | None, *, now: str
) -> dict[str, Any]:
    """The hardcoded EMERGENCY button: trips the predicate, timestamped.

    Pure; does not touch safety flags or claims. Neither input is
    mutated.
    """
    merged = copy.deepcopy(case) if case else empty_case()
    merged.setdefault("emergency", _empty_emergency())
    merged["emergency"]["active"] = True
    merged["emergency"]["button_pressed_at"] = now
    return merged


def mark_safe(case: dict[str, Any] | None, *, now: str) -> dict[str, Any]:
    """Clears the Imminent Danger PREDICATE — never the safety flag.

    A coerced tap must not erase the disclosure: the flag (and its
    provenance) stays exactly as merge_case recorded it; only the latch
    flips off, timestamped, so the app can re-evaluate honestly next
    turn rather than pretending the tap never happened.
    """
    merged = copy.deepcopy(case) if case else empty_case()
    merged.setdefault("emergency", _empty_emergency())
    merged["emergency"]["active"] = False
    merged["emergency"]["marked_safe_at"] = now
    return merged


def _parse(at: str | None) -> datetime | None:
    if not at:
        return None
    try:
        return datetime.fromisoformat(at)
    except ValueError:
        return None


def needs_resume_check(case: dict[str, Any] | None, *, now: str) -> bool:
    """Whether a long silence means DISPATCHER should re-ask once instead
    of silently resuming her inside EMERGENCY.

    True only while the predicate is active, a previous turn timestamp
    exists, the gap since it exceeds ``LONG_GAP_SECONDS``, and no resume
    check has already been issued for this particular gap (so it fires
    exactly once, not on every turn of a long silence).
    """
    if not is_imminent_danger(case):
        return False
    emergency = case.get("emergency") or {}
    last_turn = _parse(emergency.get("last_turn_at"))
    current = _parse(now)
    if last_turn is None or current is None:
        return False
    gap = (current - last_turn).total_seconds()
    if gap <= LONG_GAP_SECONDS:
        return False
    resume_check = _parse(emergency.get("resume_check_at"))
    # Already asked once for this gap (a resume check recorded no earlier
    # than the last real turn) — do not ask again turn after turn.
    return resume_check is None or resume_check < last_turn


def record_emergency_turn(
    case: dict[str, Any] | None, *, now: str, resume_check_issued: bool = False
) -> dict[str, Any]:
    """Records this turn's timestamp so the next turn can detect a long
    gap. When ``resume_check_issued`` is True, also records that the
    once-only re-ask has now been used for this gap."""
    merged = copy.deepcopy(case) if case else empty_case()
    merged.setdefault("emergency", _empty_emergency())
    merged["emergency"]["last_turn_at"] = now
    if resume_check_issued:
        merged["emergency"]["resume_check_at"] = now
    return merged


def merge_case(
    case: dict[str, Any] | None,
    delta: dict[str, Any],
    *,
    source: str = "extraction",
    now: str,
) -> dict[str, Any]:
    """Deterministically merges a CaseDelta into a Case; returns a new Case.

    Neither input is mutated. Rules (PRD #34 merge policy):

    * Every claim carries provenance: ``{value, source, confidence, at,
      conflicts[]}``.
    * A ``user``-sourced value wins outright and sets ``user_confirmed``.
      A later disagreeing extraction or document is recorded as a Conflict
      on the claim — it never reverts the confirmed value.
    * Safety flags are add-only. A delta with no flags leaves existing
      flags untouched; no source — extraction or document — can clear one.
      Re-adding an existing flag keeps its original provenance.
    * The detected language on the delta is recorded on the Case; a delta
      without one leaves the previous recording in place.

    Args:
        case: The current Case, or None for a first turn.
        delta: A CaseDelta plain dict: optional ``language``, optional
            ``claims`` mapping field -> {value, confidence}, optional
            ``safety_flags`` list of flag names.
        source: Who authored this delta; one of CLAIM_SOURCES.
        now: ISO-8601 timestamp recorded as each touched claim's ``at``.
    """
    if source not in CLAIM_SOURCES:
        raise ValueError(f"Unknown claim source: {source!r}")
    merged = copy.deepcopy(case) if case else empty_case()
    merged.setdefault("claims", {})
    merged.setdefault("safety_flags", {})
    merged.setdefault("language", None)
    merged.setdefault("emergency", _empty_emergency())

    if delta.get("language"):
        merged["language"] = delta["language"]

    for field, incoming in (delta.get("claims") or {}).items():
        value = incoming.get("value")
        if value is None or value == "":
            continue
        confidence = incoming.get("confidence", "medium")
        existing = merged["claims"].get(field)
        if source == "user":
            merged["claims"][field] = {
                "value": value,
                "source": "user",
                "confidence": "high",
                "at": now,
                "user_confirmed": True,
                "conflicts": list(existing.get("conflicts", [])) if existing else [],
            }
        elif existing and existing.get("user_confirmed"):
            if value != existing["value"]:
                # A confirmed value is never reverted; the disagreement is
                # kept as a first-class Conflict on the claim.
                existing.setdefault("conflicts", []).append(
                    {
                        "value": value,
                        "source": source,
                        "confidence": confidence,
                        "at": now,
                    }
                )
        else:
            merged["claims"][field] = {
                "value": value,
                "source": source,
                "confidence": confidence,
                "at": now,
                "conflicts": list(existing.get("conflicts", [])) if existing else [],
            }

    # Safety flags: add-only, by design the only operation that exists.
    for flag in delta.get("safety_flags") or []:
        if flag in SAFETY_FLAGS and flag not in merged["safety_flags"]:
            merged["safety_flags"][flag] = {"source": source, "at": now}
            if flag in ACUTE_SAFETY_FLAGS:
                # A newly-disclosed acute flag trips the Imminent Danger
                # latch. A textual "I'm okay" later does not clear this —
                # only mark_safe touches "active", and it never touches
                # the flag recorded above.
                merged["emergency"]["active"] = True
                merged["emergency"]["flag_triggered_at"] = now

    return merged
