---
status: accepted
date: 2026-09-04
---

# One Case per user; Conversations are threads over it, and writes persist mutations

## Decision

**One Case per user.** A user may have many Conversations (the
user-facing name for an ADK Session), but exactly one Case — held in
user-scoped state (`users/{uid}/adkUserState/{appName}`), not in
per-session state. Her country, tenure, claims, and Safety Flags are
facts about *her*, not about a thread. A per-Conversation Case means she
discloses `CONFINED` and `PASSPORT_WITHHELD` in one thread, opens
another, and that thread's DISPATCHER is safety-blind: it re-asks
questions she already answered under duress, and FILING_SEQUENCER can
hand her a plan that ignores confinement.

**One live Plan per user, likewise.** The Plan is user-scoped state
beside the Case. Asking for filing steps in a second Conversation never
builds a rival plan: it shows the live one, or regenerates *that* one
under ADR-0006's rules with DONE steps preserved. Nothing in the rules
corpus needs two: multiple grievances are already one interleaved plan
(`SequencerIn.grievances` is a tuple and every `PlanStep` carries its
grievance), a country or tenure change is sequential and handled by the
`input_hash` staleness check, and a relative filing on her behalf is an
`executor` attribute on a route, never a second subject. Two plans would
mean two orderings of identical facts with no way to reconcile what she
has already filed — the exact wobble ADR-0006 exists to prevent.

**Writes persist the mutation, not the merged blob.** An event carries
the CaseDelta (or the named mutator, for `press_emergency_button` /
`mark_safe` / a one-tap correction) plus its source and timestamp. The
session service re-runs the pure merge *inside* the Firestore
transaction, against the freshly-read stored Case, and writes the
result.

The previous shape — compute the merged Case in memory, then
`stored_user.update({"case": <blob>})` inside the transaction — is a
lost-update bug that predates multi-Conversation and is already a safety
bug on a single session: she taps EMERGENCY while a DISPATCHER turn is
in flight, the turn commits a Case computed before the tap, and
`emergency.active` is silently erased. The existing revision guard does
not save it, because the retry re-applies the same stale blob. Across
two Conversations there is not even a revision conflict to detect.
Re-merging is safe to do late because the merge policy is order-tolerant
by design: Safety Flags are add-only, and disagreements accumulate as
Conflicts rather than overwrite.

## Considered options

- **Case per Conversation** — rejected: safety-blind threads, as above.
- **Hybrid: Case per Conversation, Safety Flags and the Imminent Danger
  latch promoted to user scope** — rejected: it splits one merge policy
  across two stores, and the fields that would stay per-thread (country,
  tenure) are exactly the ones `SequencerIn` reads.
- **Keep blob writes; add a `revision` counter on the user-state
  document and replay the turn on conflict** — rejected: replay means
  another model call, and the collision that matters most is the one
  during an emergency, which is precisely when there is no latency to
  spend.

## Consequences

- The Imminent Danger latch is *not* covered by this ADR: it belongs to
  a Conversation, not the user (see ADR-0009).
- Concurrent Conversations see each other's facts but not each other's
  transcripts. The Case is the memory; the transcript is not. DISPATCHER
  may therefore know something it cannot point at in this thread.
- `_most_recent_session()` stops being a meaningful way to find "her"
  session and is removed from the button and `mark_safe` paths.
- The Case needs a plain `GET` seam: it is no longer owned by a turn, so
  it must be readable without sending a message.
- **A Conversation is created by her first message, never by a "new
  conversation" tap.** `/api/chat` already behaves this way, and it makes
  an empty, unlabellable row in the rail structurally impossible rather
  than something to sweep up later.
- **Its label is derived once and then sticks.** `list_sessions` loads no
  state, so the label is denormalised onto the session document, written
  by code at the end of the turn where the first identifiable topic
  fires. A label that tracked the *latest* topic would rename the row she
  remembers as "the passport one" to "Filing steps", defeating the rail's
  only job. Her own rename always wins.
- **Labels derive from Case claims only, never from Safety Flags.** A
  flag-derived label would put `PHYSICAL_ASSAULT_ONGOING` in her sidebar
  permanently, on a screen someone else may read — the same harm the
  neutral Emergency label avoids, through a side door. Claims name a
  subject rather than an allegation, so `passport_location` yields
  "Passport and papers" without saying who has it or why. Fixed
  precedence: `passport_location` → Passport and papers;
  `months_unpaid`/`monthly_salary` → Wages; `contract_available` → Your
  contract; `agency_name` → Your agency;
  `job_role`/`tenure_months`/`employer_name` → Your job; otherwise a
  neutral date. `country`/`location_now` are excluded deliberately —
  nearly every first message carries one, so they would swallow every
  row. A conversation that is only a safety disclosure therefore gets a
  date label, which is also the least revealing row in the list.
- Grievances cannot drive labels: they are DISPATCHER's own judgment
  passed to `SequencerIn` and never stored as Case claims, so they only
  become observable once FILING_SEQUENCER fires — far too late for most
  conversations.
- **A shared Case crosses conversations; a transcript never does.** Each
  Conversation keeps its own ADK Session and its own context window; the
  only thing carried is the Case block pasted into the instruction. Facts
  so carried are simply used — Gabay does not announce where they came
  from.
- **Re-openable conversations make scrollback a second surface for stale
  deadlines.** A three-week-old transcript still contains its Plan card,
  with steps and `expires_at` values that the one live Plan may have
  since replaced — ADR-0006's "expired deadline she acts on", reached by
  scrolling instead of by asking. Cards carrying deadlines therefore
  collapse in past turns to a line that opens the live Plan. Cards
  without a clock (contact data, verdicts, past proof gaps) replay
  unchanged.

## Amendment (issue #70): the Plan needs the mutation treatment too

This ADR's "writes persist the mutation" decision, as originally written,
only covered the Case. Moving `plan` / `plan_seq_in` / `plan_active` to
`user:` scope removes their only PRIOR concurrency guard: they used to
live in per-session state, protected by the session document's
`revision` check, but user-scoped state has no revision guard at all —
and the whole point of this ADR is to enable concurrent Conversations.
Left as plain blobs, this reopens the exact class of lost-update bug the
Case fix closes, concretely:

- the plan-staleness recheck (run every turn, unconditionally) writes
  `plan_active` from whichever Plan copy it loaded at THAT turn's start;
  a second Conversation's stale copy could overwrite `plan_active=True`
  a first Conversation just verified with a stale `False`;
- marking a step done writes the entire Plan blob, so a stale writer
  could silently discard a newer version and its completed steps;
- a failed regeneration invalidating a Plan could null out a Plan
  another Conversation had just published.

The Plan therefore gets the same treatment: `publish`, `mark_step_done`,
and `recheck_staleness` are recorded as mutations (`app.plan_ops`,
mirroring `app.case.apply_mutations`) and re-applied inside the same
Firestore transaction against the freshly-read stored Plan, never a
turn-start snapshot. `publish`'s reconcile/verify/publish decision runs
through one shared pure core (`app.plan_ops.republish`) used both by
FILING_SEQUENCER's tool (which needs an answer that turn, computed
against the turn-start Plan) and by the mutation replay (recomputed
against whatever is ACTUALLY stored) — the two agree bit-for-bit
whenever there is no concurrent writer, and only diverge, correctly, when
one exists.
