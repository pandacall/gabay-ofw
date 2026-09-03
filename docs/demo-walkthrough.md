# Demo walkthrough — Gabay OFW (issue #49)

A scripted, human-executed pass over the deployed Cloud Run URL. This is
the intent of end-to-end testing for this project, kept deliberately
**manual**: DISPATCHER routes each turn live against the real Gemini model,
so the exact tool call it makes varies run to run — a recorded
conversation replay would flake on a harmless routing variation and get
ignored, which defeats the point. What must never vary is the **outcome**
each step below checks for; that is what you are actually verifying.

This document does not replace the automated CI-gating tests
(`tests/test_route_auth_boundary.py`, `tests/test_dev_ui_absent.py`,
`tests/test_pin_audit.py`, and the full `tests/` suite) — those prove the
deployment itself is safe to demo. This walkthrough proves the *product*
behaves as PRD #34 promises, on the real deployed URL, with the real
model. **Run it twice, start to finish, against the deployed URL, before
the judged demo.** File a GitHub issue for anything that deviates from an
"Expected" line below — including a deviation that only shows up on one
of the two passes.

## Before you start

- Open the deployed Cloud Run URL in a browser. Sign in with a Google
  account when prompted (Firebase Authentication).
- Use the chat entry point from the dashboard (not the older "Crisis
  Help" card — that is a separate, pre-v6 feature; every step below
  exercises DISPATCHER, the v6 single-conversation agent from PRD #34).
- Nothing below requires more than one signed-in browser tab, or DevTools
  — every step, including EMERGENCY/mark_safe (7) and panic_wipe (8), is
  exercised through a real UI control.
- Type messages in whatever language feels natural. The reply language is
  a closed set (issue #67 ruling): English is the default — turn 1, before
  a language is known, and for English input — while Tagalog/Filipino
  input gets a pure Filipino reply and Cebuano/Bisaya input gets a pure
  Cebuano reply. Taglish input is detected but never produced: it also
  gets a pure Filipino reply, never a mixed one. See `app/agent.py`'s
  `ACKNOWLEDGEMENTS` / `acknowledgement_for` and the DISPATCHER/EMERGENCY
  instructions.
- After each step, note the wall-clock time of the first character of the
  reply appearing. The Cloud Run service should now hold one warm
  instance (`--min-instances=1`, issue #49) — if any step's *first*
  message of the session takes 10+ seconds to produce a first token, file
  it as a finding; that is the exact regression this setting exists to
  prevent.

---

## 1. SA unpaid-wages narrative → verified, cited Plan

**Do:** Start a new conversation. Say something like:

> Hindi ako nababayaran, kasalukuyan pa akong nagtatrabaho sa Saudi Arabia.

("I'm not being paid; I'm still currently working in Saudi Arabia.")

Answer any one or two clarifying questions DISPATCHER asks (e.g. how long
unpaid, whether you're still with the employer).

**Expected:**
- A warm, non-judgmental acknowledgement appears almost immediately (this
  is the fixed turn-1 acknowledgement — it should never wait on a model
  call).
- Within the same turn or the next, a **Plan card** renders: an ordered
  list of filing steps, each carrying a rule citation (a named source,
  e.g. Musaned/HRSD Friendly Settlement) and a status.
- Every step's citation is visible and non-empty — a Plan step with no
  citation is a bug, not a demo detail to skip past.
- The reply text never states a bare date or phone number that isn't
  also shown in a step or a card (DISPATCHER's after-model voice
  whitelist — see `tests/test_voice_whitelist.py`).

**Why this matters:** the ordering *is* the product (PRD #34) — this is
the core "verified Plan" promise, not a chatbot answer.

---

## 2. Correction on a SequencerIn field → Plan flips inactive + Safe Floor

**Do:** In the same conversation as step 1, look at the **Case** panel
(the right-hand summary of what the app understood). Find the "Country"
claim and tap its pencil/edit icon, or simply tell DISPATCHER in the
next message:

> Pasensya, Qatar na pala ako ngayon.

("Sorry, I'm actually in Qatar now.")

**Expected:**
- The Plan card from step 1 is no longer shown as current. In its place,
  a **Safe Floor card** renders with `reason: FACTS_CHANGED` and a
  reason line explaining that your Plan needs updating because a fact it
  was built on changed.
- This must happen even on a turn where DISPATCHER's reply text doesn't
  mention a Plan at all — the staleness check (`is_input_stale`, ADR-0006)
  is a pure function run every turn, never a judgment call.
- If DISPATCHER re-sequences (calls FILING_SEQUENCER again) for the new
  country, the regenerated Plan must carry over any step you had already
  marked DONE, and must not silently renumber steps you were mid-way
  through — a "what changed" delta, not a fresh, unexplained list.

**Why this matters:** an OFW acting on a stale ordering after her facts
changed is exactly the failure PRD user story 35 exists to prevent.

---

## 3. KW (Kuwait) narrative → fixed HELD refusal

**Do:** Start a fresh conversation (or continue, if DISPATCHER asks which
country). Say:

> Nasa Kuwait ako, hindi ako nababayaran.

("I'm in Kuwait, I'm not being paid.")

**Expected:**
- No invented filing sequence appears. Kuwait and the UAE are HELD
  jurisdictions (no verified rule corpus yet) — you should instead see a
  **held-refusal card**: an honest "we don't have a verified filing order
  for Kuwait yet" message, with the MWO Kuwait contact and the OWWA
  **1348** hotline number both present and correctly rendered.
- The reply should never fabricate a step-by-step sequence for Kuwait to
  fill the gap — a plausible-sounding but unverified order is a worse
  outcome than an honest refusal.

**Why this matters:** PRD user story 9 — an honest refusal beats an
invented sequence every time.

---

## 4. DEBUNKER — the placement-fee claim → FALSE with cited rebuttal

**Do:** In a conversation, say:

> May utang pa daw ako sa placement fee.

("They say I still owe a placement fee.")

**Expected:**
- A **verdicts** line appears with one entry: `verdict: FALSE`.
- The rebuttal names its source (2016 Revised POEA Rules / DMW, Rule V,
  Section 51 — no placement fee may be charged to a domestic worker) and
  states plainly that there is nothing to repay.
- DISPATCHER's own reply text stays in its own voice and does not
  contradict the verdict.

**Try also (HELD-adjacent honesty check):** ask something the corpus
doesn't cover, e.g. "Sabi nila makukulong daw ako pag tumakas" ("they say
I'll go to jail if I run away") — expect `verdict: NOT_COVERED` and
routing to the MWO, never a bare "I don't know."

**Why this matters:** planted beliefs ("utang mo ang placement fee") are
named in the PRD's Problem Statement as a primary control mechanism used
against her; a wrong or hedged answer here is a safety failure, not a
quality nitpick.

---

## 5. PROOF_BUILDER — single-artifact ask

**Do:** Say:

> Wala akong contract. Ano ang dadalhin ko sa MWO?

("I don't have a contract. What should I bring to the MWO?")

**Expected:**
- A **proof_gap** line appears with `next_ask` naming exactly **one**
  concrete, obtainable artifact — expect a remittance receipt offered as
  the substitute for the payslip nobody issues her (`substitute_for:
  payslip`). Not a checklist dump, not zero artifacts, not two at once.
- If you reply that you can't get that artifact either, the next ask
  should never repeat an artifact you already said you can't obtain —
  it should either substitute again or explain the plan proceeds around
  the gap.

**Why this matters:** PRD user story 16 — minutes on a watched phone
means the capture window is real; asking for a checklist instead of one
ranked artifact wastes it.

---

## 6. COMPLAINT_DRAFTER — SEnA PDF, and the unlicensed-agency refusal

### 6a. Filled SEnA form (licensed agency path)

**Do:** Say you want to file a SEnA complaint and, when asked for your
recruitment agency, give the name **"Sample Overseas Manpower Services,
Inc."** (a fixture entry seeded as LICENSED pending the live DMW query
integration — see `app/complaint/agency.py`). Answer the follow-up
questions about your employer, dates, and amounts owed as DISPATCHER asks
for them.

**Expected:**
- A **complaint_draft** line appears with a filled draft: `red_team:
  {cleared: true}` and a `sena_rfa_pdf_base64` field.
- Decode that field (or use the UI's download action, if present) and
  confirm it opens as a real PDF starting with the `%PDF` file signature
  — a byte-for-byte filled DOLE SEnA Request for Assistance form, not a
  placeholder.
- The draft is never auto-submitted anywhere; it is a document for you to
  review before you file it yourself.

### 6b. Unlicensed-agency refusal

**Do:** Start this scenario fresh (new conversation, or make clear you're
asking about a different agency) and give the agency name **"Placeholder
Global Recruitment Corp."** (fixture-seeded as DELISTED).

**Expected:**
- No SEnA form is produced. Instead, an `illegal_recruitment_refusal`
  with `reason: UNLICENSED_AGENCY` appears — routed to the DMW
  anti-illegal-recruitment track instead of a labor money claim, because
  SEnA is the wrong instrument here.
- Nothing under `draft` is populated alongside the refusal.

**Why this matters:** PRD user story 25 — the wrong venue on the first
try means starting over, at 1am, with less trust left.

---

## 7. EMERGENCY button (zero model calls) + mark_safe

**Do:**
1. Sign in normally in the browser. The red **EMERGENCY** button is always
   visible in the top-left corner, on every screen — dashboard, chat,
   Crisis Help, and Profile alike (issue #64). Tap it.
2. Watch how fast the action card renders — it should feel instant, not
   like a normal chat turn. This path (`POST /api/emergency/button`) never
   touches Gemini; it renders a fixed, cached MWO/OWWA action card and
   trips the Imminent Danger predicate with zero model latency.
3. Once EMERGENCY has been pressed, an **"I'm safe now"** button appears
   next to it (this is the mark_safe affordance — PRD user story 28/33; it
   only shows while `case.emergency.active` is true). Tap it.
4. A confirmation dialog appears ("Confirm you are safe") — this is the
   deliberate second tap so a coerced pocket-tap on the visible button
   alone can't clear the predicate (user story 32). Tap **"Yes, I am
   safe"**.

**Expected:**
- The action card renders immediately after step 1 — MWO/OWWA contacts,
  dialability-filtered for whatever country your Case currently records —
  with **zero** added latency from a model call.
- After step 4, a status toast confirms you were marked safe, and the
  "I'm safe now" button disappears (the predicate is cleared).
- Any safety flag you'd disclosed earlier in the same conversation (e.g.
  `PASSPORT_WITHHELD`) is still present in the Case panel afterward —
  `mark_safe` clears the predicate, **never** the flag itself (PRD user
  story 33).
- Tapping "I'm safe now" and then **Cancel** in the confirmation dialog
  must not clear anything — the button stays visible and no request is
  sent, proving the second tap is load-bearing, not decorative.

**Why this matters:** PRD user story 28 — help has to survive a dead
model, a dead session store, or a dead connection; user story 32 — a
coerced tap can't erase her disclosure or a pocket-tap can't fake her
safety.

---

## 8. panic_wipe leaves nothing

**Do:** Open the Profile screen (avatar → Profile). Scroll to "Delete
everything" and tap the wipe button; confirm the prompt.

**Expected:**
- A success confirmation appears, and you are signed out immediately
  afterward.
- Sign back in: your Case, chat history, and any notes are gone — a
  brand-new empty conversation, not a stale one.
- (Optional, if you have backend access) confirm no documents remain
  under `users/{uid}` in Firestore — the deletion is recursive, per
  ADR-0007, not just a top-level document.

**Why this matters:** PRD user story 38 — the wipe promise has to be
literally true, not "mostly" true, for someone deciding whether it's safe
to keep using the app on a phone that might be searched.

---

## Recording results

For each of the two full passes, log:

| # | Scenario | Pass 1 | Pass 2 | Issue filed? |
|---|----------|--------|--------|---------------|
| 1 | SA unpaid wages → verified Plan | | | |
| 2 | Correction → Plan inactive + Safe Floor | | | |
| 3 | KW → HELD refusal | | | |
| 4 | DEBUNKER placement fee → FALSE | | | |
| 5 | PROOF_BUILDER single ask | | | |
| 6a | COMPLAINT_DRAFTER SEnA PDF | | | |
| 6b | COMPLAINT_DRAFTER unlicensed refusal | | | |
| 7 | EMERGENCY button + mark_safe | | | |
| 8 | panic_wipe | | | |

A pass is only a pass if every row's "Expected" held on the real deployed
URL, with the real model — not a mocked or replayed run. Two full,
independently-run passes (not the same pass viewed twice) are the human
gate this PR cannot substitute for.
