# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: **Filipino Overseas Foreign Workers (OFWs) in the Gulf corridor** —
Saudi Arabia, Qatar, Kuwait, UAE — most often domestic workers. She is
frequently reaching for the app under stress or duress: mid-employment with
conditions that don't match her contract, possibly confined, her passport
withheld, her phone possibly monitored or shared, on a metered mobile
connection, with a narrow unwatched window to act. She may not read English
comfortably and thinks and types in Tagalog, Bisaya, Taglish, or English. The
persona used across design and docs is "Maria Villanueva, a domestic worker in
Riyadh."

Secondary, and only ever as an attribute of a route rather than the subject of
one: a family member in the Philippines who may need to place a call on her
behalf (Manila-relay dialability).

## Product Purpose

Gabay OFW ("gabay" is Filipino for *guide*) is a single Gemini-powered
conversational agent an OFW talks to in her own words. It does two jobs inside
one conversation:

1. compares what is actually happening at her job against the POEA/DMW standard
   employment contract and Gulf-jurisdiction rules, ending in a Findings Report
   and — where a verified corpus exists — an ordered filing Plan whose every
   step carries a rule citation;
2. when danger is disclosed, or the EMERGENCY button is pressed, triages the
   situation and routes her to real-world help (1343 Actionline, OWWA 1348, her
   country's MWO).

Success is that she leaves with a specific, correct next action and the right
real phone number to call — or an honest "we don't have a verified answer for
that yet" in place of a plausible invention. It never gives legal advice and
never counsels anyone through active danger; it hands off to people who can.

## Positioning

- **One Case per user, shared by every Conversation.** Her country, tenure, and
  Safety Flags are facts about *her*, not about a thread, so no conversation can
  be safety-blind to what she disclosed in another (ADR-0008).
- **Danger is its own Conversation** with an Imminent Danger latch. Disclosing a
  hazard never auto-switches anything; marking safe clears the latch but never
  the underlying Safety Flag (ADR-0009).
- **Real-world routing is code-owned.** Hotlines, MWO contacts, and directory
  links are resolved server-side from a hardcoded table; the model emits only a
  Triage Category. No phone number is ever composed by the model or hardcoded in
  the client (ADR-0002).
- **Every Case claim carries provenance** `{value, source, confidence, at,
  conflicts[]}`. A document — often a substituted contract, the fraud itself —
  never automatically outranks her narrative, and her narrative never silently
  overwrites a document on file. A Conflict is a first-class object, resolved
  only by her one-tap correction.
- **Source Tier authorization bound** (ADR-0005): TIER_1 (statute, official
  government guidance, ILO material under a government agreement) may assert hard
  dates and direct irreversible actions; TIER_2 (reputable NGO/ILO analysis) may
  only direct reversible protective steps and states dates as reported, not
  relied upon. Warnings ship at full strength regardless of tier.
- **HELD jurisdictions.** Where there is no verified rule corpus (currently
  Kuwait and the UAE) the product refuses to produce a filing sequence and shows
  an honest held-refusal with real contacts. An invented order is treated as a
  worse outcome than no order.
- **The EMERGENCY exit renders a fixed cached card with zero model calls**, so it
  works when the model, the session store, or the connection is down.
- **Progress Trail.** While a turn runs she sees fixed, code-owned labels of what
  the app is doing — never model-authored narration, never a raw tool name.

## Operating Context

- **Jurisdictions:** Saudi Arabia and Qatar have a verified rule corpus; Kuwait
  and the UAE are HELD (honest refusal only). "Gulf corridor" is the stated
  scope.
- **Institutions are named by their real names** so she can match a sign or a
  website: DMW (Department of Migrant Workers, formerly POEA), OWWA, MWO
  (Migrant Workers Office, formerly POLO-OWWA), DOLE-SEnA, 1343 Actionline, OWWA
  hotline 1348, Saudi Musaned / HRSD Friendly Settlement. MWO contact details are
  always linked out to dmw.gov.ph, never hardcoded.
- **Specialist pipeline** (DISPATCHER topology, PRD #34 / ADR-0004): Interviewer
  (gathers Claims one question at a time), Rule-Matcher (produces the Findings
  Report exactly once), DEBUNKER (verdicts on planted beliefs — e.g. "you owe a
  placement fee" → FALSE with a cited rebuttal), FILING_SEQUENCER (the one live
  Plan per user — ordered, cited filing steps), RECOURSE_ROUTER (which legal
  recourses are open and who can execute each), PROOF_BUILDER (asks for exactly
  one concrete, obtainable artifact at a time — e.g. a remittance receipt as the
  substitute for the payslip nobody issues her), COMPLAINT_DRAFTER (fills a real
  DOLE SEnA Request-for-Assistance PDF for a licensed-agency money claim; routes
  an unlicensed or delisted agency to the anti-illegal-recruitment track instead;
  never auto-submits anything).
- **Reply language is a closed set** (issue #67): English is the default (turn 1,
  before a language is known, and for English input); Tagalog/Filipino and
  Taglish input get a pure Filipino reply; Cebuano/Bisaya input gets a pure
  Cebuano reply. Taglish is detected but never produced. Language is never a
  setting the user picks or can get wrong.
- A typical session is minutes long on a possibly-watched phone. The first
  acknowledgement is fixed and never waits on a model call; one warm Cloud Run
  instance is kept so first-token latency stays low.
- **Retention and deletion** (ADR-0007): "Delete everything" (panic wipe)
  recursively removes the entire `users/{uid}` subtree *and* both device-local
  storage keys, then signs out — the device is the threat model. Crisis-related
  sessions carry an `expireAt` and auto-delete via Firestore TTL. Deleting a
  single Conversation removes only that transcript, never the Case.

## Capabilities and Constraints

- Web app. Python 3.11 · FastAPI · google-adk ≥ 2.0 · Firebase Authentication
  (Google Sign-In only) · Cloud Firestore (per-user isolation enforced by
  security rules, not client filtering) · Gemini (AI Studio) · Google Cloud
  Secret Manager (the Gemini key is never in source or env files) · Cloud Run
  (asia-southeast1). The frontend is vanilla static HTML/CSS/JS served directly —
  no build step, by intent.
- **One live Plan per user** (ADR-0006): asking for filing steps in a second
  Conversation shows or regenerates the same Plan (DONE steps preserved,
  staleness re-checked every turn by a pure input-hash function), never a rival
  ordering.
- **Safety Flags are a closed enum** (`PHYSICAL_ASSAULT_ONGOING`,
  `PHYSICAL_ASSAULT_PAST`, `THREAT_OF_HARM`, `CONFINED`, `PASSPORT_WITHHELD`),
  add-only: any source may add one, none may clear one. Only an authenticated UI
  action clears the Imminent Danger predicate — never the flag.
- The stream is line-delimited JSON; the client silently ignores line types it
  does not recognise, so backend and frontend slices ship independently
  (ADR-0010).
- **Terminology** (`CONTEXT.md` is the glossary — keep to it): *Conversation* (a
  chat thread she can leave and return to; never "check", "thread", or "chat" as
  the name of the row), *Case*, *Conflict*, *Safety Flag*, *Findings Report*
  (never "verdict", "diagnosis", "legal opinion"), *Severity*
  (`informational` / `concerning` / `urgent`), *Triage Category*, *Escalation
  Handoff*, *Progress Trail*, *Plan*. "Check" is only the verb Gabay performs
  inside a Conversation.
- Voice and contract-photo capture controls, where present, are prototype
  affordances only: they acknowledge a tap without claiming recording, camera,
  upload, or saved data.

### Retired / stale (do not treat as current truth)

- `CONTEXT.md`'s **"Modes"** section — user-selected "Contract Check" vs "Crisis
  Help" chosen from a dashboard — is retired. The product is one DISPATCHER
  conversation with an always-visible EMERGENCY button and an in-thread
  Escalation Prompt; there is no mode picker.
- `README.md`'s **"four-language copy"** line is stale: there are three reply
  languages (English, Filipino, Cebuano).
- The old `docs/design/DESIGN.md` ("Dawn One Accent" — warm clay/sand,
  Newsreader / Karla, two-mode dashboard) was removed; `DESIGN.md` at the repo
  root is the current visual authority.

### Open decisions

Continuation beyond the Cloud Run AI Challenge is possible but unconfirmed.
Jurisdiction coverage beyond Saudi Arabia and Qatar, a possible fourth language,
and a real DMW agency-license lookup (currently fixture-seeded) are roadmap
items, not commitments. No formal accessibility conformance target has been set.

## Brand Commitments

- **Name:** Gabay OFW; short form **Gabay** (Filipino for "guide"). The mark is a
  plain rotated square in pine green — deliberately generic.
- **"The aesthetic is borrowed, the brand is not."** The design may echo a
  familiar calm-assistant surface, but Gabay never wears another product's
  identity: the home-screen glow is drawn from the Philippine flag's own blue,
  red, and gold, never a generic assistant blue.
- **Voice:** calm, plain, direct, on her side. Short sentences. It invites her to
  talk in her own words rather than fill a questionnaire, opens with "Kumusta",
  and treats "I am not sure" as a real answer. It states plainly and early what
  it is *not* — not legal advice, not an emergency service.
- **Color meaning is load-bearing.** Pine green `#1F5E4A` is Gabay. Flag red
  `#CE1126` is reserved for urgent affordances only (EMERGENCY,
  delete-everything, an urgent finding) and is never decorative. Severity is
  carried first by a word and by weight; color is supplementary.
- **Findings are always framed "appears to conflict with"**, never as a
  definitive ruling. The decision belongs to DMW, OWWA, or a lawyer, and the
  product says so.

## Evidence on Hand

- Live deployment: `https://gabay-ofw-417534361115.asia-southeast1.run.app`
- Built for the Hack2skill GenAI Academy APAC **Cloud Run AI Challenge**.
- Verified rule and argument corpora in-repo: `docs/rules-corpus.md`,
  `docs/debunker-corpus.md`, `docs/recourse-router.md`,
  `docs/safe-floor-dialability.md`.
- Scripted human demo: `docs/demo-walkthrough.md` — eight scenarios, run twice
  against the deployed URL before a judged demo.
- Design canvas (held outside the repo): `Gabay OFW v6.dc.html` — the current
  visual direction the frontend is matched to.
- **Fixtures, not real integrations:** the DMW agency-license lookup is seeded
  (`Sample Overseas Manpower Services, Inc.` = LICENSED;
  `Placeholder Global Recruitment Corp.` = DELISTED). MWO phone numbers,
  distances, and office-open status must never be fabricated in the UI — real
  values are server-owned data only.
- No real testimonials, user counts, partnerships, or endorsements exist; future
  work must not invent them.

## Product Principles

1. **One agent, one conversation, one Case.** She talks; Gabay routes. No modes
   to pick, no screens to navigate to — findings and help arrive in the thread
   she is already in.
2. **An honest "we don't have a verified answer" beats a confident invention** —
   every time, on rules, numbers, and jurisdictions alike.
3. **The device is the threat model.** Help survives a dead model or connection;
   a wipe is literally complete; a coerced tap can't erase a disclosure and a
   pocket-tap can't fake safety.
4. **Real-world facts are code-owned and provenance-bound** — phone numbers,
   offices, citations, dates — never model-authored.
5. **She is the subject of every route and correction.** Her narrative is never
   silently overwritten, her one tap resolves every conflict, and the family is
   only ever a route attribute.

## Accessibility & Inclusion

- Designed for operation under stress and possible surveillance: large legible
  type that holds on a phone, generous touch targets, a fixed always-reachable
  EMERGENCY exit on every screen and inside the first-run dialog, and a
  deliberate second confirming tap on safety-clearing actions.
- Language is detected, never selected — the user cannot land in the wrong
  language by mistake. Office names stay verbatim across all languages so they
  can be matched against a physical sign.
- Assumes a metered, low-bandwidth mobile connection and a warm first response
  that never blocks on the model.
- No formal WCAG conformance target has been set (open decision).
