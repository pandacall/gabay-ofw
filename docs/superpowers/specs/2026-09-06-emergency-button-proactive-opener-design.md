# The Emergency button opens with a voice, not just a card

Status: implemented
Related: issue #41 (EMERGENCY path), issue #74 / ADR-0009 (danger is its
own Conversation), `app/chat.py`, `app/agent.py`, `app/emergency.py`,
`app/history.py`

## Problem

Tapping "I need help now" today is a dead drop. The button renders a
zero-model Safe Floor card (a list of real offices) and opens the
Emergency Conversation, and then **nothing happens until she types**.
EMERGENCY only speaks after her first message — DISPATCHER sees it and
transfers. For someone who has just hit a panic button, a wall of phone
numbers followed by silence is a cold first contact.

The user wants an agent to open the conversation: greet her, ask what is
happening, and offer to help — while keeping the card as the instant,
model-independent safety net it is today.

## Decisions

Resolved with the user before writing this spec; each is a real
trade-off, not an assumed default.

1. **One opening message, then wait.** EMERGENCY posts a single proactive
   message and stops. It does not drive a multi-question triage from the
   tap — that would take the conversation away from her before she has
   said a word. Her first typed reply then flows through the existing
   DISPATCHER → EMERGENCY path, entirely unchanged.
2. **The opener is model-generated, and degrades to nothing.** A fixed
   code-owned line was considered and rejected: it cannot reflect what
   she has already disclosed (country, months unpaid, a withheld
   passport). The model opener degrades to *silence* rather than to a
   canned sentence — and silence is honest here, because the card is
   already on screen. If the model is down, slow, or errors, she keeps
   the card and the conversation, sees no error, and the opener simply
   does not appear.
3. **The opener is its own request, fired only for a fresh Conversation.**
   The card and conversation open exactly as today — zero model calls,
   never gated on anything. Only then does the frontend call a new
   endpoint, `POST /api/emergency/opener`. Folding it into
   `/api/emergency/button` was rejected: it would hold that stream open
   for the model call, turning "instant card" into "instant once the
   model answers". A second press *reopens* the Emergency Conversation
   (ADR-0009) and must **not** re-greet, so `press_emergency_button`
   starts reporting whether it created or reopened.
4. **This amends ADR-0009's first consequence bullet.** That bullet says
   the button path makes zero model calls. It now makes zero model calls
   **for the card and the Conversation**; a best-effort opener turn
   follows and may make one. The card is still what bounds the "nothing
   changes unless she taps" gap — the number she needs is on screen
   whether or not the opener ever renders. This is an explicit, accepted
   departure, recorded here rather than as a new ADR (matching the
   precedent set by `2026-09-05-llm-conversation-titles-design.md`, which
   overrode an ADR-0008 invariant the same way). If it turns out wrong,
   the fix is to drop the opener endpoint and its one frontend call; the
   button path is untouched underneath it.
5. **Button only.** The Escalation-Prompt confirmation path
   (`escalate_from_prompt`) is unchanged — it already opens carrying a
   one-line handoff summary. A proactive opener there can come later.

## Non-goals

- Not changing the card, the latch, the Case, `mark_safe`, the
  at-most-one-live-Emergency-Conversation rule, or the DISPATCHER →
  EMERGENCY transfer.
- Not changing `_emergency_instruction` or `_dispatcher_instruction`. The
  opener's framing rides in the synthetic message content, so both agent
  instructions stay a single code path.
- Not adding a proactive opener to the Escalation-Prompt path.
- Not streaming the opener from `/api/emergency/button`.

## Design

### Flow

1. She taps → `POST /api/emergency/button` streams, exactly as today:
   `card` (zero-model cached Safe Floor), then `emergency_latch`, then
   `case`. The `emergency_latch` line gains a `created: bool` field.
2. Frontend `pressEmergencyButton` renders the transcript
   (`openConversation`) and the card, exactly as today.
3. **New:** if `created` is true, the frontend calls
   `POST /api/emergency/opener` and renders its `trail` / `reply` lines
   live through the existing `handleChatLine`. A failure is caught
   silently — no error bubble.

### `EMERGENCY_OPENER_TRIGGER` (`app/emergency.py`)

A module-level constant: a fixed, model-facing stage direction, e.g.

> `[She just opened this Emergency Conversation from the help button and
> has not said anything yet. Greet her warmly in her language, reflect
> what her Case already shows without re-asking it, and in the same short
> message ask whether she wants you to help her think through what to do
> next or whether she just needed the phone numbers. Ask nothing else.]`

Exported. Used as the Runner's `new_message` text by the opener endpoint,
and matched exactly by `replay_conversation` to suppress it.

### `stream_emergency_opener` (`app/chat.py`)

New `ChatService` method, mirroring `stream_turn`'s Runner loop but
minimal:

- Look up the user's live Emergency Conversation via the same
  `EMERGENCY_CONVERSATION_ID_RAW` user-state pointer
  `_open_or_reopen_emergency_conversation` uses. No live Emergency
  Conversation → the endpoint returns 404 (mirrors `/api/chat`).
- Drive one Runner turn with `new_message` = `EMERGENCY_OPENER_TRIGGER`.
  The latch is active, so `_dispatcher_instruction` returns its
  "transfer to EMERGENCY immediately" instruction; EMERGENCY speaks.
- Yield `trail` lines (from function calls, as `stream_turn` does) and
  the `reply` line(s) from `event.author == "EMERGENCY"`. Never yield a
  `user` line for the trigger.
- Wrap the whole thing so any exception is logged and swallowed: the
  stream just ends with no `reply`. The endpoint still returns 200.

`record_turn` on EMERGENCY runs as normal, so `EMERGENCY_RESUME` is
written and the long-silence resume clock starts from the greeting.
ROUTING_GUARD's after-model whitelist runs on the opener like any voice
turn — the opener carries no numbers, so it passes; a fabricated number
would be scrubbed exactly as elsewhere.

### `_open_or_reopen_emergency_conversation` / `press_emergency_button`

- The helper returns `(session_id, case, created: bool)` — `created` is
  false on the early-return reopen branch, true after `create_session`.
- `press_emergency_button` puts `created` on the `emergency_latch` line.

### `replay_conversation` (`app/history.py`)

Skip a `user`-authored event whose joined visible text equals
`EMERGENCY_OPENER_TRIGGER`, so the synthetic message never renders as her
bubble on re-open. (The live opener stream never emits a `user` line, so
no change is needed there.)

### `POST /api/emergency/opener` (`app/main.py`)

Auth-gated like every `/api/*` route. Streams
`service.stream_emergency_opener(uid=uid)` as `application/x-ndjson`.
404 when there is no live Emergency Conversation.

### Frontend (`static/app.js`)

`pressEmergencyButton`: capture `created` from the `emergency_latch`
line. After `openConversation` + the card push, if `created`, `fetch`
the opener endpoint and `readNdjsonLines(response, handleChatLine)`.
Wrap in `try/catch` with an empty catch — the opener is decorative
relative to the card. No change to the instant-card path.

### Race

She may type before the opener returns. `append_event` is transactional
with one retry (ADR-0003); the worst case is the best-effort opener
losing the race and being dropped. Accepted.

## Testing

### Backend (`tests/test_emergency.py`)

- The opener endpoint streams a `reply` authored by EMERGENCY after a
  button press; zero effect on the latch and Case.
- The opener is **persisted**: re-opening the Emergency Conversation
  (`GET /api/conversations/<id>`) shows the greeting as a `reply`, and
  the `EMERGENCY_OPENER_TRIGGER` never appears as a `user` line.
- Model raises during the opener → endpoint still 200, no `reply` line,
  the card and conversation from the button press are intact.
- No live Emergency Conversation (opener called without a prior button
  press / after `mark_safe`) → 404.
- Whitelist: an opener turn that emits a fabricated number has it
  replaced and logged (reuse the `TestEmergencyVoiceWhitelist` pattern).
- `press_emergency_button`: `emergency_latch.created` is true on first
  press, false on the second (reopen).

### Replay (`tests/test_history_replay.py`)

- A stored Conversation containing a `user` event equal to
  `EMERGENCY_OPENER_TRIGGER` replays with no `user` line for it, and the
  following EMERGENCY `reply` still replays.

### Frontend (`frontend-tests/emergency.spec.js`)

- After a first press, the opener request fires and its `reply` renders
  in the thread.
- Opener endpoint 500 → the card is still shown, no error bubble.
- Second press (reopen, `created: false`) → the opener request does not
  fire.

### Regression

- Existing `TestHardcodedButtonZeroModelCalls` still passes unchanged:
  the button stream itself makes zero model calls.
