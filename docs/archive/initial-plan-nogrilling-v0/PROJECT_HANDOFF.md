# Gabay OFW — Project Handoff

Handoff doc for moving implementation from planning (Claude) to coding (GitHub Copilot). Everything here reflects the state of the project as of **2026-08-31**. Copilot: also read `.github/copilot-instructions.md` in this repo — it's the condensed, always-loaded version of the rules below.

## 1. The event and the deadline
- **Hack2skill "GenAI Academy APAC" — Cloud Run AI Challenge track.**
- Start: 25 Aug 2026, 09:30 PM IST. **Hard deadline: 07 Sep 2026, 02:29 AM IST.**
- Submission needs, all publicly working: a live Cloud Run URL (or a walkthrough video if not kept running), a public GitHub/GitLab repo with a README (deploy steps, config, Firestore rules), a demo social post with **#AccelerateAIwithCloudRun**, and a brief description covering how Firebase, Firestore, Cloud Run, and Gemini were used.

## 2. Mandatory checklist (all four must be true and demonstrable)
- [ ] User authentication via **Firebase Authentication**
- [ ] Genuine **multi-turn** interaction with the **Gemini API** (via AI Studio) — not single-shot Q&A
- [ ] **User-isolated Firestore** document storage (enforced by security rules, not just client filtering)
- [ ] Secure API key retrieval via **Google Cloud Secret Manager**
- [ ] Any additional tech used beyond this must be mentioned explicitly in the Brief Description

After deploying to Cloud Run, apply the label **`dev-tutorial=cloud-run-ai-challenge`** — missing this breaks the mandatory checklist even if everything else works.

Judged on four criteria: **Authenticity** (originality beyond the starter template), **Usability** (clean sign-on, error-free flows), **Stability** (error handling, uptime), **Security** (hardened Firestore rules, key handling, access controls).

## 3. The concept: what Gabay OFW is
"Gabay OFW" — Tagalog for "guide" (renamed 2026-08-31 from the original working name "OFW Shield"; unrelated to Robin's separate personal project also named "Ligtas OFW", hence the rename). A Gemini-powered app for Filipino Overseas Foreign Workers deployed specifically to the **Gulf corridor** — Saudi Arabia, UAE, Qatar, Kuwait — with two modes, chosen explicitly by the user from a dashboard:

1. **Contract Check** — a multi-turn conversation where the user describes their actual working conditions; the app compares that against known POEA/DMW standard employment contract rules and returns a structured findings report (issue, rule cited, severity: informational / concerning / urgent).
2. **Crisis Help ("I Need Help Now")** — a short, calm triage conversation that determines the situation and routes the user to the correct real-world resource (OWWA hotline, 1343 Actionline, or the country-specific embassy/MWO). This mode is explicitly **triage and routing only** — it must never attempt to counsel someone through active danger itself.

**Why mode selection is a UI choice, not automatic classification**: an LLM misclassifying a crisis message as a contract question (or vice versa) is a safety failure, not just a UX papercut. This was a deliberate call made early in planning and should not be "optimized away" later.

## 4. Competitive landscape and why this doesn't claim category novelty
Vetted across two rounds of research before committing to this concept (see the reasoning trail if you want the full history — it lived in Claude project docs `claude/baseline-research-and-concepts.md` and `claude/ofw-shield-build-plan.md`). Known overlaps, accepted deliberately:
- **VeriJob** — pre-employment job-offer/recruiter scam scoring for OFW-hopefuls. Different problem (pre-deployment vs. this app's in-deployment focus).
- **PoBot / Migrasia** — in-country rights chat for OFWs, but covers HK/PH/Indonesia/Taiwan corridors, explicitly **not the Gulf**.
- **Bantay OFW**, the OWWA 1348 hotline infrastructure, 1343 Actionline, and a possible CFO panic-button app — existing crisis-response channels.

Differentiation is **execution, not category invention**: Gulf-corridor focus (UAE alone accounted for 397,892 of ~2.7M 2025 OFW deployments — the single largest destination), real Tagalog/Taglish/Bisaya handling, POEA-SEC-grounded contract analysis, and a genuinely privacy-conscious data design (see §7). Be upfront about this in the Brief Description and demo — judges reward honest framing over inflated novelty claims.

## 5. Known non-negotiable OFW contract rules (grounding content — do not alter, do not add salary figures)
- Passport confiscation by employer/agency is illegal, always, regardless of contract wording.
- Minimum 1 rest day per week; premium pay if worked.
- Overtime paid at POEA SEC rate or host-country rate, whichever is higher.
- Contract substitution (a different/worse contract signed abroad than the DMW-verified one) is illegal.
- Repatriation cost at contract end / early termination without just cause is the employer's responsibility.
- Standard contracts include medical/dental coverage during the term.

Do **not** hardcode specific salary minimums — they vary by occupation and country and change over time. Always direct users to dmw.gov.ph for current figures.

Source: batasko.com/ofw/ofw-contract-rights, POEA Memorandum Circular 63-A.

## 6. Escalation resources
- OWWA 24/7 Hotline: **1348** (stable, safe to hardcode)
- 1343 Actionline Against Human Trafficking: **1343** (stable, safe to hardcode)
- Country-specific POLO-OWWA / Migrant Workers Office (MWO) contacts: **do not hardcode** — link out to the official DMW directory (dmw.gov.ph). Numbers, addresses, and dialing formats change per country; a stale hardcoded crisis contact is actively dangerous, not just an inconvenience.

## 7. Firestore data model
```
users/{uid}
  profile: { destinationCountry, occupation }   # optional, user-entered

users/{uid}/contractChecks/{checkId}
  { status, flags: [...], severity, createdAt }
  /messages/{msgId}                             # conversation turns

users/{uid}/crisisSessions/{sessionId}
  { country, routedTo, timestamp, expireAt }
  /messages/{msgId}                             # conversation turns
```
**Privacy design choice**: `crisisSessions` documents carry an `expireAt` field with a Firestore TTL policy configured on that collection (e.g., auto-delete 48–72h after creation), so a stored "my passport was taken" transcript doesn't persist indefinitely somewhere an abusive employer with device access could find it. This satisfies the mandatory "user-isolated Firestore storage" checklist item while being a genuinely stronger Security-criterion story than the base Codelab template's default (which stores everything indefinitely). Users can also manually delete a session at any time — build that control in.

Firestore security rules must enforce `request.auth.uid == uid` on every path under `users/{uid}/...`.

## 8. System prompts (draft v1)
These are written at the content level — they describe what each conversational step needs to do, independent of whether it ends up implemented as one Gemini call, an ADK agent, or something else. See `.github/copilot-instructions.md` for the exact prompt text (Contract Check / Interviewer step, Rule-Matcher step, Crisis mode) — kept there so it's always in Copilot's context.

## 9. Multi-agent architecture — STATUS: DECIDED 2026-09-01 (see `docs/adr/0001-adk-workflow-architecture.md`)
**Decision**: Contract Check is an **ADK 2.0 graph `Workflow`** — Interviewer `LlmAgent` looping with the user via HITL (`ResumabilityConfig` + `RequestInput`), a deterministic completeness-check *function node* deciding the route, and a Rule-Matcher `LlmAgent` firing exactly once when claims are complete. Crisis Help is a **single `LlmAgent`**, never a pipeline. Mode routing stays a UI choice (§3).

Key rationale and constraints (full detail in the ADR):
- `SequentialAgent` was rejected — it would run the Rule-Matcher on every user turn against incomplete claims. The 2.0 Workflow graph gives idiomatic ADK *and* deterministic routing in unit-testable function nodes.
- Requires `google-adk >= 2.0`, Python >= 3.11.
- ADK session services have no Firestore TTL support → custom Firestore session layer implementing §7's `expireAt` design is required.
- Tue 2 Sep spike must prove: pause/resume across HTTP requests on Cloud Run; session persistence coexisting with TTL; Rule-Matcher firing exactly once.
- **Fallback ladder**: not cleanly working end-to-end by **Wed 3 Sep 6pm** → same two agents, explicit orchestration in app code; catastrophe → single structured Gemini call per mode.

## 10. Build plan (day-by-day; today = Mon 31 Aug)
Weekdays are for building; weekends are buffer/double-check only — no new features once Saturday starts.

- **Mon 31 Aug** (done): system prompts drafted, clickable UI prototype built, sprint-plan tracker built.
- **Architecture-decision session** (before Tuesday's build work starts): separate, code-free discussion to resolve §9.
- **Tue 1 Sep**: init public GitHub repo; confirm language (Python); build the AI Studio scaffold (Firebase Auth + Firestore + Gemini shell); wire Firebase Auth + base Firestore rules; first Cloud Run deploy of the skeleton (get a live URL early); wire Secret Manager. Plus a spike: a minimal end-to-end handoff test of whatever the architecture session decided, on one canned example, outside the real UI.
- **Wed 2 Sep**: build the real Contract Check pipeline into the actual screen + Firestore persistence, informed by Tuesday's spike. Fallback per §9 still applies if the chosen approach struggles.
- **Thu 3 Sep**: build Crisis Help flow, country-aware routing, Firestore TTL setup on `crisisSessions`.
- **Fri 4 Sep** (last build day): Tagalog/Taglish/Bisaya prompt tuning; error handling for Gemini API failures and malformed JSON; input sanitization against prompt injection in pasted contract text; empty/loading states.
- **Sat 5 Sep** (buffer, no new features): OWASP Top 10 Web + OWASP Top 10 LLM self-audit; Firestore rules hardening pass fixing only what the audit finds; confirm the Cloud Run label is applied; full click-through of both flows end to end.
- **Sun 6 Sep** (buffer, packaging not code): record the demo video, write the README (deploy steps, config, Firestore rules, architecture actually used), write the brief description, post with #AccelerateAIwithCloudRun, final check that the live URL/repo/social post are all public and working, submit with buffer before the Mon 02:29 AM IST cutoff.

## 11. Design reference (not production code)
A clickable UI prototype and a live sprint-plan tracker exist as Claude Design canvas artifacts, titled **"Gabay OFW"** and **"Gabay OFW Sprint"** respectively. Use them as the UI/UX and copy-tone reference (screen flow, language-toggle pattern, card/severity styling) — they're static/scripted demos, not wired to real Firebase/Gemini, so don't treat their code as a starting implementation.

## 12. Security checklist (OWASP Top 10 Web + OWASP Top 10 for LLM Apps)
- Firestore rules enforce per-user isolation on every path, not just client-side query filters.
- All user input (especially pasted contract text) is treated as untrusted before reaching a Gemini prompt — guard against prompt-injection attempts trying to override system instructions.
- Gemini's structured JSON output is validated against a strict schema before being trusted or persisted — never directly render model output as raw HTML/markup.
- The model never fabricates a phone number, embassy address, or legal citation — anything not in the grounded reference list routes to the official DMW/OWWA site instead.
- No secrets (API keys, service account JSON) in source, committed `.env` files, or client bundles — Secret Manager / Cloud Run secret bindings only.
- Reasonable rate-limiting or cost bounds on Gemini calls per user.
- Crisis-mode transcripts are not written to general application logs — they live only in the user-isolated, TTL'd Firestore path.
- All Contract Check output is framed as "appears to conflict with standard POEA/DMW rules," never as definitive legal advice.

## 13. Tooling split (for context, not a hard rule)
Robin's stated plan: **Google AI Studio** for scaffolding/deployment, **GitHub Copilot** for custom coding (this handoff), **Claude** for security review, brainstorming, and writing deliverables (README, brief description, social post). Bring things back to Claude for a security/OWASP pass before submission, and for help drafting the README and brief description once the build is functionally done.
