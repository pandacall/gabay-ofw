---
status: accepted
date: 2026-09-01
---

# Single store: custom Firestore SessionService for ADK session state

ADK Workflow resumption needs a persistent session store, and ADK ships none for Firestore. We implement a custom Firestore-backed `SessionService` so session state lives inside the existing user-scoped paths (`users/{uid}/...`), rather than adding `DatabaseSessionService` (Cloud SQL) as a second store. Rationale: a second store would hold crisis transcripts outside the reach of our Firestore security rules and the `expireAt` TTL policy, quietly breaking the privacy design that is our main Security-criterion differentiator. Scope guard: implement only the `SessionService` methods a resumable Workflow actually exercises (determined by the Tue 2 Sep spike); if the interface proves too deep, that triggers the ADR-0001 fallback ladder, not a switch to a second store.
