"""The Case: structured facts merged deterministically from CaseDeltas.

``merge_case`` is a pure function (PRD #34, merge policy): provenance is
recorded per claim, user-confirmed values are never reverted by a later
extraction (a disagreement becomes a Conflict on the claim), and safety
flags sit outside precedence entirely — a delta may ADD a flag and may
NEVER clear one. There is deliberately no code path that removes a flag:
only an authenticated UI action clears (out of scope for this slice;
issue #44's one-tap correction endpoint only ever writes a claim, never a
flag).

A Conflict is a first-class Case object, never a UI event (issue #44):
``{value, source, confidence, at}`` entries accumulate on
``claim["conflicts"]``, resolved only by a later ``user``-sourced claim
(the one-tap correction). Two rules produce a Conflict instead of an
overwrite: a claim already ``user_confirmed`` is never reverted by any
other source, and a claim contested across DIFFERENT non-user provenance
(extraction vs document, in either order) is never silently resolved
either — the document is frequently the fraud (a substituted contract),
so it can never silently outrank her narrative, but her narrative also
never silently overwrites a document already on file. Same-source
updates (a later extraction refining an earlier one) still overwrite
directly — that is progressive refinement within one channel, not a
disagreement across sources.

Everything stored in the Case is a JSON-serialisable plain dict so it can
live in ADK session state and in Firestore unchanged.

Acute Safety Flags (issue #41, PRD #34): acuteness is a property of the
safety-flag enum member itself — ``ACUTE_SAFETY_FLAGS`` is a frozenset in
code, never a side table. ``PHYSICAL_ASSAULT_ONGOING`` and
``THREAT_OF_HARM`` are acute; ``PHYSICAL_ASSAULT_PAST`` is not.
``CONFINED`` and ``PASSPORT_WITHHELD`` are chronic baseline (near-universal
per Amnesty) and are never acute on their own.

Pending Escalation (ADR-0009, issue #74): when ``merge_case`` records a
NEW acute flag it sets ``case["pending_escalation"]`` — an acute flag
disclosed and not yet acted on. It is NOT the Imminent Danger latch: it
transfers nobody anywhere. The latch moved off the Case entirely and onto
the Conversation (``app.emergency`` / ``app.state_keys.EMERGENCY_LATCH``),
because "this Conversation is the Emergency one" is Conversation state,
while the Safety Flags that provoke it are facts about her and stay here.
``app.chat.stream_turn`` draws the Escalation Prompt from a newly-added
acute flag; a declined prompt needs no bookkeeping because flags are
add-only, so a flag is only ever *new* once.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

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

#: Acute-class flags record a Pending Escalation on their own (ADR-0009).
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


def empty_case() -> dict[str, Any]:
    """A fresh Case: no claims, no flags, no recorded language."""
    return {
        "claims": {},
        "safety_flags": {},
        "language": None,
        "pending_escalation": None,
    }


def _record_conflict(
    claim: dict[str, Any], *, value: Any, source: str, confidence: str, now: str
) -> None:
    """Appends a Conflict entry to ``claim`` in place, deduping by
    ``(value, source)``: a disagreement that recurs turn after turn (the
    same document re-processed, the same fact re-extracted) updates the
    existing entry's ``at``/``confidence`` instead of piling up duplicate
    entries the UI would otherwise render as separate tappable options.
    """
    conflicts = claim.setdefault("conflicts", [])
    for entry in conflicts:
        if entry.get("value") == value and entry.get("source") == source:
            entry["confidence"] = confidence
            entry["at"] = now
            return
    conflicts.append(
        {"value": value, "source": source, "confidence": confidence, "at": now}
    )


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
    * A claim contested across two DIFFERENT non-user sources (extraction
      vs document, either order) is likewise never silently overwritten:
      the disagreeing value is recorded as a Conflict and the existing
      value stands until her tap resolves it. Only a same-source update
      (extraction refining its own earlier reading, or a second document)
      overwrites directly — that is refinement, not a disagreement.
    * Safety flags are add-only. A delta with no flags leaves existing
      flags untouched; no source — extraction or document — can clear one.
      Re-adding an existing flag keeps its original provenance.
    * A NEW acute flag records a Pending Escalation on
      ``case["pending_escalation"]`` (ADR-0009): ``{flag, at}``. It trips
      no latch and transfers nobody — ``app.chat.stream_turn`` shows the
      Escalation Prompt from the newly-added acute flag.
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
    merged.setdefault("pending_escalation", None)
    # ADR-0009: the Imminent Danger latch left the Case for Conversation
    # state. A Case persisted before that migration keeps a now-dead
    # ``emergency`` dict; drop it on the next write so it never lingers.
    merged.pop("emergency", None)

    if delta.get("language"):
        merged["language"] = delta["language"]

    for field, incoming in (delta.get("claims") or {}).items():
        value = incoming.get("value")
        if value is None or value == "":
            continue
        confidence = incoming.get("confidence", "medium")
        existing = merged["claims"].get(field)
        if source == "user":
            # Her tap IS the resolution: any Conflict a prior turn raised
            # on this field is resolved by this write, never carried
            # forward — otherwise a field could never unblock sequencing.
            merged["claims"][field] = {
                "value": value,
                "source": "user",
                "confidence": "high",
                "at": now,
                "user_confirmed": True,
                "conflicts": [],
            }
        elif existing and existing.get("user_confirmed"):
            if value != existing["value"]:
                # A confirmed value is never reverted; the disagreement is
                # kept as a first-class Conflict on the claim.
                _record_conflict(existing, value=value, source=source, confidence=confidence, now=now)
        elif (
            existing
            and existing.get("source") != source
            and existing.get("value") != value
        ):
            # Cross-provenance disagreement with no user tap yet (e.g. her
            # narrative said 11 months unpaid, a payslip says 14): neither
            # side silently wins. The document is frequently the fraud, so
            # it never outranks her narrative automatically — but her
            # narrative doesn't silently overwrite a document already on
            # file either. Both values persist; only a later ``user``
            # correction (the one-tap resolution) picks one.
            _record_conflict(existing, value=value, source=source, confidence=confidence, now=now)
        else:
            merged["claims"][field] = {
                "value": value,
                "source": source,
                "confidence": confidence,
                "at": now,
                "conflicts": list(existing.get("conflicts", [])) if existing else [],
            }

    # Safety flags: add-only, by design the only operation that exists.
    for flag in sorted(delta.get("safety_flags") or []):
        if flag in SAFETY_FLAGS and flag not in merged["safety_flags"]:
            merged["safety_flags"][flag] = {"source": source, "at": now}
            if flag in ACUTE_SAFETY_FLAGS and (
                merged.get("pending_escalation") is None
                or merged["pending_escalation"].get("at") != now
            ):
                # A NEW acute flag records a Pending Escalation (ADR-0009):
                # noted, not yet acted on. NO latch, NO transfer — the
                # Escalation Prompt is drawn from this by the conversation
                # spine. A declined prompt needs no bookkeeping: flags are
                # add-only, so a flag is only ever new once. When two
                # acute flags land the same turn the first (sorted) wins
                # the record; either way the reason category covers both.
                merged["pending_escalation"] = {"flag": flag, "at": now}

    return merged


# ---------------------------------------------------------------------------
# Sequencer-blocking conflicts (issue #44, PRD #34 merge policy).
# ---------------------------------------------------------------------------

#: Case claim fields that feed FILING_SEQUENCER's typed input
#: (``SequencerIn``: country, tenure, grievances). An unresolved Conflict
#: on any of these blocks FILING_SEQUENCER — a wrong jurisdiction or a
#: disputed tenure duration would build a Plan around a contested fact.
#: Conflicts elsewhere (e.g. ``employer_name``) are informational only.
#:
#: Only fields that actually exist as Case claims today are listed:
#: ``country`` maps 1:1 onto ``SequencerIn.country``, and
#: ``tenure_months`` is the closest existing proxy for
#: ``SequencerIn.tenure`` (extraction has no other tenure-shaped field).
#: ``SequencerIn.grievances`` has no corresponding Case claim at all — it
#: is derived by DISPATCHER's own judgment from the conversation, never
#: written to ``case["claims"]`` with provenance — so it cannot be
#: checked here; a real per-grievance Conflict mechanism is future work.
SEQUENCER_FIELDS = frozenset({"country", "tenure_months"})



# ---------------------------------------------------------------------------
# Mutation replay (ADR-0008): a Case write persists the mutation that
# produced it, not the merged blob computed in memory. The session
# service re-runs this pure replay INSIDE its Firestore transaction,
# against the freshly-read stored Case — closing the lost-update bug
# where a turn already in flight when a concurrent write lands commits a
# Case computed before it and silently erases the other write.
#
# The Imminent Danger latch is NO LONGER a Case mutation (ADR-0009): it
# moved to Conversation state (``app.emergency``), which the per-session
# document's ``revision`` guard already protects. ``merge`` is the only
# Case op left.
# ---------------------------------------------------------------------------

#: The mutation shapes this build understands. Anything else is an
#: "unknown op" per ``apply_mutations``'s contract below.
MUTATION_OPS = frozenset({"merge"})


def apply_mutations(
    case: dict[str, Any] | None, mutations: list[Any] | None
) -> dict[str, Any] | None:
    """Replays recorded Case mutations onto ``case``, in order.

    Each mutation is a small JSON-serialisable record:

        {"op": "merge", "delta": <CaseDelta>, "source": ..., "now": ...}

    Pure: neither ``case`` nor any entry of ``mutations`` is mutated. A
    non-dict entry is ignored. An entry whose ``"op"`` is not ``"merge"``
    — or whose payload this build cannot make sense of (a missing
    ``"now"``, an unrecognised ``merge`` source, a malformed delta) —
    leaves ``case`` UNTOUCHED for that entry rather than raising or
    clearing it: a mutation this build cannot understand must never lose
    data.

    Safe to replay out of order, late, or twice: the merge policy itself
    is order-tolerant by construction (Safety Flags are add-only,
    disagreements accumulate as Conflicts rather than overwrite), so
    replaying a mutation against a Case that has moved on since it was
    recorded is exactly as safe as applying it the moment it was
    recorded.
    """
    for mutation in mutations or []:
        if not isinstance(mutation, dict):
            continue
        op = mutation.get("op")
        now = mutation.get("now")
        if op not in MUTATION_OPS or not isinstance(now, str) or not now:
            # Unknown (or malformed) mutation: leave the Case exactly as
            # it was for this entry, never raise, never clear anything.
            continue
        if op == "merge":
            delta = mutation.get("delta")
            source = mutation.get("source", "extraction")
            if not isinstance(delta, dict):
                continue
            try:
                case = merge_case(case, delta, source=source, now=now)
            except ValueError:
                # An unrecognised source is exactly as harmless to skip
                # as an unrecognised op above.
                continue
    return case


def unresolved_sequencer_conflict(case: dict[str, Any] | None) -> Optional[str]:
    """The first ``SEQUENCER_FIELDS`` claim carrying an unresolved Conflict.

    Returns the field name to block on, or ``None`` when every
    sequencer-relevant claim is uncontested. A Conflict is "unresolved" as
    long as its ``conflicts`` list is non-empty — resolution only ever
    happens by a ``user``-sourced claim replacing it (``merge_case``
    clears the list for that field's next write, since a fresh dict
    replaces the old one). Deterministic, no I/O.
    """
    if not case:
        return None
    claims = case.get("claims") or {}
    for field in sorted(SEQUENCER_FIELDS):
        claim = claims.get(field)
        if isinstance(claim, dict) and claim.get("conflicts"):
            return field
    return None
