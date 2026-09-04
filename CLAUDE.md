# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Gabay OFW — a Gemini-powered conversational web app for Filipino Overseas Foreign
Workers in the Gulf corridor (Saudi Arabia, Qatar, Kuwait, UAE). One agent, one
conversation: it compares her working conditions against DMW/Gulf rules and,
when danger is disclosed, triages and routes her to real-world help. Built for
the Hack2skill GenAI Academy APAC Cloud Run AI Challenge.

Python 3.11 · FastAPI · `google-adk==2.8.0` · Gemini (AI Studio) · Firebase Auth
(Google Sign-In only) · Cloud Firestore · Secret Manager · Cloud Run
(asia-southeast1). Frontend is vanilla static HTML/CSS/JS in `static/` — no build
step, by intent.

## Commands

```bash
pip install -r requirements-dev.txt      # backend + test deps
python -m pytest tests -q                 # backend tests (no cloud needed)
python -m pytest tests/test_guard.py -q   # one test file
python -m pytest tests/test_guard.py::test_name -q   # one test
```

- `tests/test_firestore_session_service.py` needs the Firestore emulator; it
  skips unless `FIRESTORE_EMULATOR_HOST` is set. CI wraps the whole run in
  `npx firebase-tools emulators:exec --only firestore --project demo-gabay-ofw`
  (needs Node 22 + JDK 21).
- Frontend (Playwright, Chromium, desktop + mobile projects): `npm ci` then
  `npm run test:ui`. `playwright.config.js` starts its own uvicorn on port 8765.
- Firestore security-rules tests: `cd rules-tests && npm install && npm test`
  (runs against the emulator; needs Node 18+ / Java 21+).
- Run locally: `uvicorn --factory app.main:production_app --port 8000` with
  `GOOGLE_CLOUD_PROJECT` and `FIREBASE_WEB_CONFIG` set (needs ADC for Firestore),
  or `app.main:create_app` for a no-cloud shell.

No linter/formatter is configured. Match surrounding style.

Push to `master` runs both test suites then deploys to Cloud Run
(`.github/workflows/deploy-cloud-run.yml`, OIDC + Workload Identity, no SA key).
The deployed container installs from `requirements-lock.txt` (a full freeze);
regenerate it whenever `requirements.txt` changes.

## Where the rules live

- **GitHub issues** are the requirement/PRD tracker. Use the `gh` CLI. Before any
  issue/PR write, follow the credential preflight in
  `docs/agents/issue-tracker.md` (Copilot sessions inject a pull-only `GH_TOKEN`
  that shadows the writable keyring login).
- **`docs/adr/`** is authoritative for architecture. Read the ADRs touching your
  area before changing it; surface conflicts rather than silently overriding.
  (Numbers 0004/0005 are referenced in prose but their files are not in-repo.)
- **`CONTEXT.md`** is the terminology glossary — use its exact terms
  (*Conversation*, *Case*, *Conflict*, *Safety Flag*, *Findings Report*, *Plan*,
  *Triage Category*, *Progress Trail*), and honour its `_Avoid_` list.
- **`PRODUCT.md`** has the product spec and a "Retired / stale" section — note
  that `README.md`'s "four-language copy" line and `CONTEXT.md`'s "Modes" section
  are both stale (there is no mode picker; three reply languages).
- **`DESIGN.md`** at the repo root is the current visual authority.

## Architecture

### Request spine (`app/main.py` → `app/chat.py`)

FastAPI app built by `create_app()`; `production_app()` adds `firebase_admin`.
Every `/api/*` route except health/config is gated by `get_current_uid`
(Firebase ID token → uid). `/api/chat` streams **line-delimited JSON (NDJSON)**;
the client silently ignores line types it doesn't recognise, so backend and
frontend slices ship independently (ADR-0010). Line types: `ack`, `trail`,
`card`, `reply`, `verdicts`, `proof_gap`, `complaint_draft`, `recourse_routes`,
`case`, `error`.

`ChatService` owns one ADK `App` + `Runner`. `stream_turn` emits a fixed
acknowledgement and the opening Progress Trail line **before any model call**,
then drives the ADK Runner and streams tool-produced cards + DISPATCHER's reply.

### Agent topology (`app/agent.py`, ADR-0004 / PRD #34)

- **DISPATCHER** — the root `mode="chat"` `LlmAgent`, the only voice the user
  hears. Its `before_agent_callback` runs `read_narrative` → `merge_case`
  (deterministic) and the plan-staleness recheck, strictly before the turn.
- **Specialists** — `FILING_SEQUENCER`, `DEBUNKER`, `PROOF_BUILDER`,
  `COMPLAINT_DRAFTER`, `RECOURSE_ROUTER` are `mode="single_turn"` sub-agents.
  google-adk 2.8.0 auto-wraps each as a tool named after the agent with its
  typed `input_schema` as params — no `AgentTool`, no free-text request param.
  Each has a Pydantic `output_schema`; its result crosses to the UI as a typed
  NDJSON line, never as prose DISPATCHER composed (ADR-0002).
- **EMERGENCY** — the *only* `transfer_to_agent` target.
  `disallow_transfer_to_parent=True` makes it a one-way door; ADK will not
  auto-resume it, so DISPATCHER's instruction re-transfers every turn while the
  Imminent Danger predicate is active. Exit is a UI tap (`mark_safe`) only,
  never inferred from her words.
- `App(...)` sets `events_compaction_config` + `context_cache_config` to bound
  per-turn replay cost as a crisis conversation grows (issue #49).
- Gemini model + `google-adk` are **exact-pinned**; never a `-latest` alias.

### ROUTING_GUARD (`app/guard.py`) — highest-consequence code

A silent failure here routes an assault victim to local police. It is a
`BasePlugin` on the App **plus** a root `before_tool_callback` on DISPATCHER —
two independent rails, not an agent. It:
- fails closed on a **tool allowlist** (`ALLOWED_TOOLS`);
- filters tool *results* by `Channel` enum (`office_directory` rows carry a
  channel; `LOCAL_POLICE` is in no permitted set; `UNKNOWN` country is the most
  restrictive, never the least); never conditioned on model-extracted flags;
- runs an **after-model whitelist diff**: every number/date in a voice agent's
  reply must be a set-membership match against values tools returned this turn
  (∪ the user's own message). Non-members are re-emitted from tool results.
- **Never return `{}` from a callback** — it silently skips the real tool. A
  refusal is a structured non-empty dict; an allow is `None`.

### Case & Plan state (`app/case.py`, `app/state_keys.py`, ADR-0008)

- **Exactly one Case per user** and **at most one live Plan per user**, shared by
  every Conversation — stored under `user:`-prefixed ADK state keys (→
  `users/{uid}/adkUserState/{appName}` in Firestore), never per-session. Always
  use the `state_keys.py` constants, never bare string literals.
- `merge_case` is pure: every claim carries `{value, source, confidence, at,
  conflicts[]}`. User-confirmed values are never reverted by extraction; a
  cross-source disagreement becomes a first-class **Conflict** on the claim,
  resolved only by a `user`-sourced correction (`POST /api/case/correct`).
- **Safety Flags** are a closed enum, add-only: any source may add one, no source
  (and no document) may clear one. Only an authenticated UI action clears the
  Imminent Danger *predicate* (`case["emergency"]["active"]`) — never the flag.
- `panic_wipe` and `mark_safe` are **nonce-gated HTTP endpoints, never agent
  tools** (guarded by `tests/test_agent_tool_guard.py`).

### Firestore session layer (`app/firestore_session_service.py`, ADR-0003)

Custom `BaseSessionService` under `users/{uid}/...` paths. `append_event` is
transactional with a `revision` counter and one retry. Case/Plan get a stronger
guarantee: `CASE_MUTATIONS` / `PLAN_MUTATIONS` ride on the event's `temp:` state
delta, and `append_event` re-runs the pure `apply_mutations` merge *inside the
transaction* against freshly-read stored state — this closes the lost-update bug
where a DISPATCHER turn in flight when she taps EMERGENCY would erase the press.

### Retention (`app/retention.py`, `app/deletion.py`, ADR-0007)

`delete_user_subtree` is the one routine that removes a user's data; panic wipe
recursively deletes `users/{uid}` *and* both device-local storage keys, then
signs out (the device is the threat model). Deleting one Conversation removes
only that transcript. Crisis sessions carry `expireAt` for Firestore TTL;
`/api/internal/retention-sweep` is a shared-secret-header endpoint for Cloud
Scheduler.

### Firestore security rules (`firestore.rules`)

Enforce `request.auth.uid == uid` on every path under `users/{uid}/...`;
everything else denied by default. Per-user isolation is enforced here, not by
client filtering. Deploy: `firebase deploy --only firestore:rules`.

## Conventions specific to this repo

- **Real-world facts are code-owned.** Phone numbers, offices, citations,
  deadlines, amounts never come from the model. `app/directory.py` is the
  immutable contact table; `action_card` takes directory *keys*, never number
  strings. An honest "we don't have a verified answer" always beats an invention.
- **Verified corpora gate behaviour.** Only Saudi Arabia and Qatar have a rule
  corpus (`app/rules/`); Kuwait and the UAE are HELD — the app refuses to
  produce a filing sequence and shows an honest refusal.
- **Reply language is a closed set** (issue #67): English default; Tagalog/Taglish
  input → pure Filipino reply; Cebuano input → pure Cebuano. Taglish is detected,
  never produced. Never a user setting. Office/form/legal names stay untranslated.
- Structural regression-guard tests scan live objects (agent trees, module
  source) rather than hardcoding — see `tests/test_agent_tool_guard.py`,
  `tests/test_dev_ui_absent.py`, `tests/test_voice_whitelist.py`. The ADK dev UI
  is never deployed.
- Do not add attribution lines to commit messages or PR descriptions.
