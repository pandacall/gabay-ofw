"""The Case: structured facts merged deterministically from CaseDeltas.

``merge_case`` is a pure function (PRD #34, merge policy): provenance is
recorded per claim, user-confirmed values are never reverted by a later
extraction (a disagreement becomes a Conflict on the claim), and safety
flags sit outside precedence entirely — a delta may ADD a flag and may
NEVER clear one. There is deliberately no code path that removes a flag:
only an authenticated UI action clears (out of scope for this slice).

Everything stored in the Case is a JSON-serialisable plain dict so it can
live in ADK session state and in Firestore unchanged.
"""

from __future__ import annotations

import copy
from typing import Any

# Safety flag enum. Acuteness (Imminent Danger) is a later slice; the flag
# vocabulary is fixed here so extraction is validated against a closed set.
SAFETY_FLAGS = frozenset(
    {
        "PHYSICAL_ASSAULT_ONGOING",
        "PHYSICAL_ASSAULT_PAST",
        "THREAT_OF_HARM",
        "CONFINED",
        "PASSPORT_WITHHELD",
    }
)

# Provenance sources. Only these may author a claim; none of them may clear
# a safety flag.
CLAIM_SOURCES = frozenset({"extraction", "document", "user"})


def empty_case() -> dict[str, Any]:
    """A fresh Case: no claims, no flags, no recorded language."""
    return {"claims": {}, "safety_flags": {}, "language": None}


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

    return merged
