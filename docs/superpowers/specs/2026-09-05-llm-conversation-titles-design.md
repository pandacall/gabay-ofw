# LLM-generated Conversation titles

Status: approved for planning
Related: issue #73, ADR-0008 (one Case per user, Conversations as threads), `app/labels.py`

## Problem

Today's Conversation label (`app/labels.py`) is a closed, five-key,
claims-only precedence table (`passport` / `wages` / `contract` / `agency`
/ `job`), write-once, renameable by her. It was deliberately built this
way, not as an oversight: a label derived from free text or from Safety
Flags risks putting an abuse detail in a sidebar her employer might see,
and a label that tracks the *latest* topic defeats the point of a stable
name she can use to find a Conversation again.

The user wants titles closer to Gemini's — a short, natural, specific
phrase generated from what was actually discussed, not one of five fixed
strings. This spec extends the existing system with an LLM-generated
title, while preserving the safety property that made the current design
closed-set in the first place: the title must never leak an allegation.

## Decisions

These were resolved with the user before writing this spec; each
represents a real trade-off, not a default assumed unilaterally.

1. **Emergency Conversations are not exempted.** The current invariant
   ("The Emergency Conversation keeps its neutral date label forever",
   `app/labels.py:26-29`) is deliberately overridden: an Emergency
   Conversation still gets a safety-filtered LLM title attempt, same as
   any other Conversation. This is an explicit, accepted departure from
   the ADR-0008 invariant — the riskiest Conversations now rely on the
   same filter as everything else, rather than being hard-excluded from
   generation entirely. If this turns out wrong in practice, the fix is
   to reinstate the `EMERGENCY_CONVERSATION` exclusion in
   `label_state_delta`-equivalent logic for the LLM path specifically.
2. **Safety filtering is deterministic code, not a second model call.**
   Consistent with ROUTING_GUARD's own pattern elsewhere in this codebase
   (fail closed, code-owned, never conditioned on model self-report), the
   filter is a plain-code check against a fixed blocklist plus structural
   rules (no digits, length cap) — never an LLM asked "is this safe?".
3. **Generate once per Conversation, in the background, after the first
   turn.** Not retried across turns (unlike the claims-based system,
   which is a cheap pure function and keeps trying every turn). One
   background attempt (with up to 2 retries within that attempt — see
   below), fire-and-forget after her first reply has already streamed, so
   title generation never adds latency to her conversation.
4. **On safety-filter rejection: retry up to 2 times (3 attempts total),
   then fall back.** Each retry adds an instruction to be more generic,
   without echoing the specific blocked term back to the model (avoids
   teaching it to word-swap around the blocklist). If all 3 attempts are
   rejected, or the call errors out on all 3 attempts, nothing is
   written — the existing claims-based `derive_label()` keeps running
   every turn exactly as it does today, so it is the fallback with no new
   fallback code needed.
5. **Titles are always English**, regardless of the conversation's reply
   language (EN/Fil/Ceb). Simplifies the blocklist to one vocabulary.

## Non-goals

- Not replacing the claims-based system — it remains the fallback and
  the only mechanism for Emergency Conversations if this feature is ever
  rolled back for them.
- Not changing rename behavior — her own rename still always wins,
  permanently, exactly as today.
- Not adding a new NDJSON line type — the title becomes visible the same
  way current labels do, on the next conversation-list fetch, since
  listing already reads `conversation_label` from session state fresh
  each time (`app/labels.py:44-52`).

## Design

### Data flow & storage

No schema change. Same two session-state keys
(`CONVERSATION_LABEL`, `CONVERSATION_LABEL_SOURCE`) get a third possible
source value, `"llm"` (alongside today's `"derived"` and `"user"`), and
the label value itself is the literal generated string, shown verbatim
(same as a rename) rather than looked up as a localization key.

A new state key, `conversation_title_llm_attempted` (bool), records that
the one-time background attempt happened — regardless of outcome — so it
is never retried on later turns. Written at the end of the attempt,
alongside `CONVERSATION_LABEL`/`CONVERSATION_LABEL_SOURCE` on success, or
alone on exhaustion of retries/errors.

Trigger point: after DISPATCHER's first reply in a Conversation has
finished streaming to the client (mirrors where `label_state_delta` is
already invoked in `app/chat.py`, but gated additionally on "this is the
first turn and `conversation_title_llm_attempted` is not set"), kick off
the generation as a background task. It writes its result via the same
transactional session-state mutation path Case/Plan mutations already use
(`app/firestore_session_service.py`'s `apply_mutations`-inside-transaction
pattern), so a concurrent turn in flight can't lose the write.

Order relative to the existing claims-based check: the background LLM
attempt and the existing per-turn `label_state_delta` claims check are
independent and both idempotent against the write-once latch
(`CONVERSATION_LABEL` presence). Whichever writes first wins; in practice
the LLM attempt will usually resolve first since it fires right after
turn one, before a claims-worthy second turn typically arrives.

**Operational constraint (Cloud Run):** "background, after the reply
streams" must mean FastAPI's `BackgroundTasks` (or an equivalent that
keeps the work inside the same request's lifecycle), not a detached
`asyncio.create_task` outside the request scope. Cloud Run's default
CPU-allocation mode only guarantees CPU during active request
processing; a truly detached task risks being frozen mid-call once the
instance decides the request is done. This is a constraint for the
implementation plan to satisfy, not a new design decision — it doesn't
change any behavior described above, only how "background" must be
implemented to actually run to completion.

### Generation call

- **Input**: her opening message + DISPATCHER's first reply text (not
  her whole future conversation — this is a one-shot attempt at turn
  one).
- **Model**: same pinned Gemini model already used elsewhere in this
  codebase (exact-pinned, never a `-latest` alias, per existing
  convention) — not a new model dependency.
- **Output**: structured via `response_schema`, a single field
  `title: str`. No ADK agent/tool wrapping — this is a direct
  out-of-band call from `app/chat.py`'s turn-completion code, the same
  shape as today's `derive_label()` trigger, not a `mode="single_turn"`
  specialist. It does not enter ROUTING_GUARD's tool allowlist or
  callback surface.
- **Prompt constraints**: 3-6 words; describes only the administrative/
  legal category of her situation, in the spirit of the existing five
  categories but phrased more specifically and naturally (e.g. "Unpaid
  wages, several months" rather than the fixed string "Unpaid wages");
  a generic "General inquiry" category when nothing more specific fits.
  Explicitly forbidden: incident specifics, numbers, dates, names,
  locations, threats, or any wording implying violence, confinement, or
  an emergency.
- **Retry prompt**: on rejection, the retry call adds an instruction to
  produce a more generic, administrative-only phrase, without repeating
  or hinting at the specific blocked word/phrase from the prior attempt.

### Safety filter (deterministic, code-owned)

Runs in plain code after each generation attempt, before any write:

1. Reject if the title contains any digit character (current labels
   never show numbers either — consistent with existing UI convention).
2. Reject if the title exceeds a fixed character length.
3. Reject if the title case-insensitively contains any blocklist term.
   The blocklist has two parts:
   - Terms derived from the closed `SAFETY_FLAGS` enum in `app/case.py`
     (`PHYSICAL_ASSAULT_ONGOING`, `PHYSICAL_ASSAULT_PAST`,
     `THREAT_OF_HARM`, `CONFINED`, `PASSPORT_WITHHELD`) — e.g. assault,
     hit, beat, threat, confine, lock(ed) in, withhold(ing)/confiscat(ed)
     passport. Note the distinction from the existing `passport` claims
     category: "Passport and papers" (administrative, fine) vs.
     "employer withheld passport" / "confiscated passport" (implies the
     `PASSPORT_WITHHELD` flag, blocked) name the same topic but only one
     is safe to show — the blocklist targets the allegation phrasing, not
     the subject.
   - A small curated list of generic hard-stop terms not tied to a
     specific flag: kill, suicide, rape, blood, hospital, weapon, gun,
     knife, and minor/child-abuse terms.

Any single rejection triggers the retry-or-fallback flow in Decision 4
above — never a second model call to decide safety.

### Frontend

One change: `conversationRowLabel()` in `static/app.js:664-669` currently
branches — `"user"` source renders the string verbatim; anything else is
looked up as a `convLabel_<key>` localization string. Add `"llm"` to the
verbatim-string branch alongside `"user"`. No other UI changes.

### Error handling

A call that errors (timeout, API failure) rather than being filtered is
treated identically to a filter rejection for retry/fallback purposes —
same 3-attempt budget, same silent fallback to the claims-based label on
exhaustion. Nothing is ever surfaced to her about title generation
failing; it's a cosmetic feature and fails invisibly.

### Testing

- Unit tests on the blocklist function: every `SAFETY_FLAGS`-derived term
  and its adversarial phrasings (case variation, partial words), every
  hard-stop term, digit-containing titles, over-length titles — all
  rejected. Legitimate category phrases from the existing five claims
  categories, phrased naturally — all accepted.
- Retry-loop test: 3 rejected attempts in a row falls back cleanly (no
  write except the `_attempted` marker); a rejection followed by an
  accepted retry writes correctly with `source="llm"`.
- Regression test that Emergency Conversations flow through the same
  code path as any other Conversation (per Decision 1) — and that the
  blocklist still catches emergency-implying language on that path
  exactly as it would elsewhere (this is the one path where filter
  correctness matters most, since the invariant that used to hard-block
  generation there no longer exists).
- Regression test confirming the existing claims-based write-once latch
  and rename-always-wins behavior are unaffected by the new code path.
