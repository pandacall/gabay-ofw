---
status: accepted
date: 2026-09-03
---

# Plan staleness: input hash and step expiry, with distinct consequences

A Plan carries `input_hash` — the hash of the `SequencerIn` it was built from — and
`Plan{plan_id, version, input_hash, steps[{id, status: PENDING|DONE|VOIDED,
rule_citation, expires_at}]}`. Staleness is decided by two pure functions run every turn,
never by DISPATCHER's judgement: (1) `hash(current_sequencer_in) != plan.input_hash` — a
field not in `SequencerIn` cannot have affected the plan, so the check cannot drift out of
sync with the sequencer; (2) wall-clock step expiry. The consequences differ, and
conflating them is the bug: expiry voids those steps while the rest stands and she keeps
acting on it; an input-hash mismatch means the ordering itself may be wrong, so the plan
stops being presented as actionable — shown inactive with "this needs updating because you
told me X" plus the Safe Floor — until a replacement clears `publish_plan`. Regeneration
is never a silent renumber: DONE steps survive (she may have already filed step 2) and the
delta is surfaced. If regeneration runs and `verify_plan` does not clear, ship no sequence
— Safe Floor plus the action card — not the unverified replacement and not the stale plan
presented as current.

## Considered options

- **Regenerate unconditionally on every case change** — rejected: DONE steps still need
  reconciling, it burns a sequencer + verify chain on irrelevant changes, and a model
  picking rows can reorder identical facts — the one artifact that matters would wobble.
- **DISPATCHER decides when to re-invoke** — rejected: a stale plan is an expired deadline
  she acts on, the same failure class as a hallucinated phone number. Determinism owns it.
