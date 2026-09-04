---
status: accepted
date: 2026-09-03
---

# Retention and deletion: one recursive path, deadline-aware silent expiry

## Decision

**One deletion routine.** A user's data is removed by exactly one code
path — `app.deletion.delete_user_subtree` — whether the trigger is
`panic_wipe` (her authenticated tap) or retention expiry (the scheduled
sweep). The two triggers differ only by a recorded reason code
(`panic_wipe` / `retention_expiry`). Two routines means one eventually
misses the transcript.

**Deletion is recursive.** Firestore deletes never cascade and native TTL
policies do not reach subcollections, so deleting `users/{uid}` alone
would orphan every session, event, and state document beneath it. The
walk uses `list_documents` so subcollections under *missing* parent
documents are found too. Expiry is therefore a scheduled recursive delete
(a sweep endpoint guarded by a shared secret, invoked by Cloud
Scheduler), not a TTL policy.

**Deadline-aware expiry.**

    expireAt = max(last_activity + BASE_WINDOW,
                   latest_live_deadline + DEADLINE_MARGIN)

The deadline component is absolute: it does not shrink with inactivity.
Qatar's claim window is a year; a rolling TTL would delete a detained
user's evidence early — the person most likely to need the record must
not be the one who loses it. `BASE_WINDOW` is 180 days and
`DEADLINE_MARGIN` is 90 days (tunable constants in `app.retention`).
Stored `expireAt` updates are monotonic: an activity-only touch (which
knows no deadlines) never shrinks a deadline-backed retention promise.
Session activity extends `expireAt` via the session service; the
Plan-publishing path supplies live deadlines when it lands.

**Expiry is silent.** No notification is ever sent — a notification about
an abandoned case naming an abuser is itself a safety incident. Data
still expires eventually so that case does not persist forever.

**`panic_wipe` and `mark_safe` are nonce-gated backend HTTP endpoints,
never agent tools.** No agent may call them; a structural test
(`tests/test_agent_tool_guard.py`) fails if any agent in the `app`
package ever registers a tool with those names. The nonce forces a
deliberate two-step from the authenticated UI and makes a replayed
request useless; nonces live in process memory only, never in Firestore.
The UI exposes the wipe control; one tap deletes the entire subtree and
the next visit starts clean.

**Rules land with the schema.** `users/{uid}.expireAt` is backend-managed:
security rules deny any client write that creates or alters it, and deny
client-side deletes of the profile document (which would bypass the
single deletion path and orphan subcollections).

## Amendment (2026-09-04): multi-Conversation deletion boundary

A user may now hold many Conversations (ADR-0008), which puts a delete
control on each row. That control is **narrower** than this ADR's single
deletion routine, and the two must not be confused.

**Deleting a Conversation removes that Conversation's transcript and
nothing else.** Her Case is user-scoped, so the claims and Safety Flags
she disclosed there survive — and the UI says so plainly, in one line,
rather than letting a frightened person assume otherwise: *"This removes
the conversation. What you told Gabay about your situation stays. To
remove everything, use Delete everything."* `delete_user_subtree` remains
the only routine that deletes a user's data, and `panic_wipe` remains
the actual safety tool.

Retracting a Conversation's claims on delete was rejected: Safety Flags
are add-only precisely so no source can quietly unsay them, and an
employer holding her unlocked phone could otherwise delete one
conversation and make the app forget she was ever confined.

**Safety Flag clearing is now defined** (this ADR previously left it as
"only an authenticated UI action clears", out of scope). Ordinary Case
claims are editable and deletable in one tap, where a delete is recorded
as a user-sourced retraction rather than a hole — otherwise a later
extraction silently refills it, against `merge_case`'s rule that a
user-sourced value is never reverted by a later source. Safety Flags sit
apart and clear only through the same nonce-gated two-step `mark_safe`
uses: clearing the flag is strictly more destructive than clearing the
latch, so it cannot be less protected.

