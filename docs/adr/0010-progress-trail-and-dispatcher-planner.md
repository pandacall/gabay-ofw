---
status: accepted
date: 2026-09-04
---

# The Progress Trail is code-owned; DISPATCHER thinks at MEDIUM

## Decision

**What the app shows while a turn runs is a fixed, code-owned phrase
keyed to what actually fired** — never the model's own narration. Labels
are translated like the acknowledgements already are, emitted as their
own NDJSON line type, and cleared when the reply lands. A tool with no
entry in the table emits nothing: the failure mode is a quiet gap, never
a raw tool name or JSON on screen.

Labels name the **task, never the hypothesis**: "Looking up your agency",
not "checking whether your agency is recruiting illegally". The trail is
read by whoever is looking at her screen, and an accusation displayed
there is the same class of harm as the notification ADR-0007 refuses to
send. The verdict itself can be blunt, because by then she has chosen to
read it.

The trail's first line is emitted **immediately after the
acknowledgement**, not on the first tool call, because thinking happens
before any tool call — so a call-triggered trail would leave the app's
one silent moment exactly where the new latency is.

**DISPATCHER gets `BuiltInPlanner` with
`ThinkingConfig(thinking_level=MEDIUM, include_thoughts=False)`.**
Specialists and EMERGENCY stay planner-free.

`thinking_level`, not `thinking_budget`: the pinned model is
`gemini-3.6-flash`, and `google-genai` states in its own field
documentation that from Gemini 3.5 onward `thinking_budget` "will no
longer be supported and will result in a user error if set". A token
budget here is a 400, not a tuning knob.

`include_thoughts=False`: thought parts arrive as
`Part(text=..., thought=True)` *inside the same event content as the
reply*, and `stream_turn` builds its reply from every part with text.
Turning summaries on without also filtering `part.thought` would splice
the model's raw reasoning into her reply, in English, during a crisis.
The filter is added regardless — configuration should not be the only
thing standing between her and that.

## Considered options

- **Surface Gemini's thought summaries as the trail** — rejected on three
  grounds. (1) *Language*: the app answers in her language throughout;
  thought summaries come back in English, so the one thing on screen
  while she waits would be the part she may not read, and translating it
  costs a second model call inside the latency window it exists to fill.
  (2) *Verifiability*: a progress line is a claim about what the system
  did. Model-authored text about fixed facts is what ADR-0002 forbids —
  a narrated corpus lookup is not evidence of a corpus lookup.
  (3) *Stability*: summaries change shape with the model version, which
  is why the model is pinned exactly rather than to a `-latest` alias.
- **`LOW`** — the argument was that DISPATCHER's thinking only composes a
  call set, and every consequential judgement in the turn (filing order,
  plan staleness, ROUTING_GUARD, the Imminent Danger predicate) is
  already code-owned, so depth buys little. Kept as the fallback if a
  representative multi-specialist turn (DEBUNKER + FILING_SEQUENCER
  together) stops fitting a ~10s budget: it is a one-constant change.
- **Suppressing the trail in the Emergency Conversation** — rejected: the
  reply text on that screen is far more revealing than any
  hypothesis-free label, so the shoulder-surfing argument does not
  survive the wording rule, and suppression would leave the longest wait
  in the app with no feedback at all.

## Consequences

- **One line per specialist, not per tool call, with verification as the
  one exception.** FILING_SEQUENCER alone runs `sequence_actions` →
  `compute_deadlines` → `verify_plan`, so a per-tool trail would stutter
  three lines through what she asked as a single question. Verification
  earns its own line because "checking these steps against the rules" is
  a distinct and true claim, and it is the most reassuring thing the
  system can say to someone a recruiter has lied to. Contact-card
  lookups stay silent — the card itself appears, which says more than a
  label could.
- The opening line cannot be "Reading what you wrote": the fixed
  acknowledgement already says exactly that ("I hear you. I'm reading
  what you wrote — one moment"). It has to be the next beat — what the
  app is about to do — or the first two lines on screen repeat.
- Thinking latency is paid in the danger path too, because DISPATCHER is
  the root and runs before transferring to EMERGENCY on every turn —
  making EMERGENCY planner-free does not by itself keep thinking out of
  an emergency. Accepted deliberately: the safety-critical artifact
  there is the hotline card, which renders with zero model calls and is
  unaffected. What waits is comfort and triage.

- `handleChatLine` ignores unrecognised line types, so the backend and
  frontend halves of the trail can ship independently.
- ROUTING_GUARD can refuse a tool after its call event fires, so a label
  may appear for a call that is then blocked. The trail is transient and
  never part of the transcript, which bounds that to a flicker.
- Cold start dominates this decision in practice: the first request also
  builds the ChatService, the Firestore client, and the agent tree. Warm
  the service before any walkthrough.
