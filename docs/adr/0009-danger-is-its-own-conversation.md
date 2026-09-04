---
status: accepted
date: 2026-09-04
---

# Danger is its own Conversation, entered only by her tap

## Decision

**The Emergency Conversation is a kind of Conversation, not a mode any
Conversation enters.** The EMERGENCY button opens a new Conversation
carrying an Escalation Handoff — country, reason category, a one-line
summary in her language, the source Conversation's ID, never the
transcript. It opens already knowing her Case (ADR-0008), so it does not
re-ask what she disclosed under duress. Her other Conversations are
untouched and keep behaving normally.

**At most one is live at a time.** If an Emergency Conversation already
holds the latch, the button reopens that one instead of creating another;
a new one is created only after `mark_safe` has closed the previous,
because a separate emergency later is a separate episode. A panic
double-tap is therefore harmless, her account of what is happening stays
in one place rather than split across rows, and `mark_safe` has exactly
one unambiguous target — so it needs no Conversation id from the UI and
its existing per-user nonce keeps working unchanged.

The Imminent Danger latch therefore belongs to the **Conversation**,
while the Safety Flags that provoke it belong to her user-scoped Case.
This is the one place the two scopes deliberately differ.

**A conversational disclosure does not hijack the thread.** When
`merge_case` records a new acute Safety Flag mid-turn, the Conversation
shows an **Escalation Prompt**: the Safe Floor card, rendered at the
same time and unconditionally, plus a two-tap offer to open an Emergency
Conversation. The card comes *with* the prompt, not after it — otherwise
the app can detect danger and then do nothing while it waits for a tap
that may never come because her phone was taken.

**Declining dismisses the prompt, never the flag.** The Safety Flag
keeps its value and provenance and still counts for FILING_SEQUENCER and
RECOURSE_ROUTER. This is the `mark_safe` rule applied to a new surface:
a coerced tap must not erase the disclosure. Declining suppresses the
prompt for *that* flag; a different acute flag prompts again, because a
second disclosure is new information rather than a repeat.

## Considered options

- **Transfer the current thread to EMERGENCY in place (the previous
  behaviour)** — rejected: it ends her contract conversation mid-question
  and staples an emergency transcript to it, and it leaves danger being
  handled inside a thread labelled "Hours and pay".
- **Any latch trip moves her automatically into the Emergency
  Conversation** — rejected: the screen changes under her while she is
  typing, at the worst possible moment. The prompt keeps the decision
  hers.
- **User-wide latch, so every Conversation enters emergency behaviour** —
  rejected: it makes her other threads unusable for the ordinary
  questions she may still want answered, and one mark_safe tap would
  govern all of them.

## Consequences

- This is the only path in the app where danger is detected and nothing
  changes unless she taps. The unconditional Safe Floor card is what
  bounds that: the number she needs is on screen either way.
- **The latch moves out of the Case and into Conversation state.** Today
  `merge_case` sets `case["emergency"]["active"]` the moment a new acute
  flag merges, and `_dispatcher_instruction` transfers on that predicate
  — which is the auto-hijack this ADR removes, and it would fire before
  she ever saw the prompt. So `merge_case` instead records a **Pending
  Escalation** (an acute flag disclosed, not yet acted on), and the latch
  is set only by the button or by her confirming the prompt, and cleared
  only by `mark_safe`. `is_imminent_danger` correspondingly changes
  meaning from "is this user in danger" to "is this Conversation the
  Emergency one" — which is what it always operationally meant.
- The declined-prompt record needs no bookkeeping of its own: Safety
  Flags are add-only, so a flag is only ever *new* once. Re-prompting for
  the same hazard is impossible by construction.
- Clearing a Safety Flag is now a defined action (it was parked as "out
  of scope" in ADR-0007) and is nonce-gated as a two-step, matching
  `mark_safe` — which clears strictly less and is already protected that
  way.
- The Emergency Conversation appears in the rail like any other. Its
  label is a neutral date, never "Emergency": a visible label naming
  what it is would be a disclosure to anyone who picks up the phone. It
  is never relabelled to a topic later.
- **She may delete the Emergency Conversation at any time, including
  while the latch is active.** Deletion is a safety action — the reason
  she deletes is that someone is about to look at her phone — so
  refusing at that moment would put the app's bookkeeping above her
  safety. The latch is Conversation state, so it goes with the
  Conversation and leaves no orphan for `mark_safe` to fail against; her
  Safety Flags survive on the Case, exactly as when she declines a
  prompt. "Help now" reopens a fresh Emergency Conversation instantly.
  The deliberate consequence: afterwards the app looks entirely
  ordinary, with nothing to explain to whoever is holding the phone.


