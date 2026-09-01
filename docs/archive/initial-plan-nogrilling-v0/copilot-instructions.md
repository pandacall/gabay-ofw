# Copilot instructions — Gabay OFW

Repo-wide context for GitHub Copilot (Chat and inline). Read this before suggesting or generating any code in this repo. If a suggestion would conflict with anything below, follow this file, not general defaults.

## What this project is
"Gabay OFW" (Tagalog: "guide") is a hackathon submission for the **Hack2skill GenAI Academy APAC — Cloud Run AI Challenge** (deadline **07 Sep 2026, 02:29 AM IST**). It's a Gemini-powered app for Filipino Overseas Foreign Workers (OFWs) deployed to the Gulf (Saudi Arabia, UAE, Qatar, Kuwait), with two user-selected modes:

1. **Contract Check** — multi-turn conversation comparing the user's actual working conditions against POEA/DMW standard employment contract rules, ending in a structured findings/severity report.
2. **Crisis Help ("I Need Help Now")** — short, calm triage conversation that routes the user to a real human resource (OWWA hotline, embassy, DMW directory). This mode must never attempt to counsel someone through a live danger itself — its only job is triage and routing.

Mode selection is an **explicit UI choice on the dashboard, never automatic classification of user intent**. Do not build or suggest an intent-classifier that silently routes between modes — a wrong classification in a crisis context is a safety risk, not just a bug. This is a deliberate, load-bearing design decision — do not "simplify" it away.

## Mandatory hackathon requirements (do not build around these)
- **Firebase Authentication** for user identity (Google Sign-In or similar) — no stored passwords.
- **Cloud Firestore** for storage, with **user-isolated document paths** (every document scoped under `users/{uid}/...`, enforced by Firestore security rules, not just by client-side filtering).
- **Gemini API via Google AI Studio**, used in genuine **multi-turn** conversations (not single-shot Q&A).
- **Secret Manager** (or equivalent Cloud Run secret binding) for the Gemini API key — **never** hardcode it, never commit it, never read it from a plain env file checked into git.
- Deploy to **Cloud Run**, and apply the label `dev-tutorial=cloud-run-ai-challenge` after deploying.
- Submission checklist these map to (all must be demonstrably true): Firebase auth ✅, multi-turn Gemini ✅, user-isolated Firestore storage ✅, Secret-Manager-based key retrieval ✅.
- Judged on: **Authenticity** (originality beyond the starter template), **Usability** (clean single-sign-on flow, error-free interactions), **Stability** (robust error handling, uptime), **Security** (hardened Firestore rules, key handling, access controls).

## ⚠️ Multi-agent architecture: NOT YET DECIDED
Earlier planning drafted a candidate design (Google ADK, 2-agent SequentialAgent: an "Interviewer" agent + a "Rule-Matcher" agent for Contract Check, single-agent for Crisis Help, deterministic UI-driven routing instead of an LLM coordinator). **This was never finalized — treat it as one option under consideration, not a decision.** A dedicated discussion session is being run separately to settle this before implementation starts.

**Do not silently pick an architecture and start scaffolding agent orchestration code.** If asked to implement "the agent pipeline" and no decision has been recorded yet (check for an updated `## Multi-agent design` section in `PROJECT_HANDOFF.md` first), ask which of these was decided, or default to the simplest safe option: **a single well-structured Gemini call per mode with a strict structured-JSON response schema**, which satisfies every mandatory requirement above without any agent-framework risk. Whatever gets decided, all system-prompt content below is written to survive either architecture — it's about content, not agent boundaries.

## Known non-negotiable OFW contract rules (grounding content — do not invent or alter these, do not hardcode salary figures since they vary by occupation/country and change; always point users to dmw.gov.ph for current minimums)
- Passport confiscation by employer/agency is illegal, always, regardless of contract wording.
- Minimum 1 rest day per week; premium pay if worked.
- Overtime paid at POEA SEC rate or host-country rate, whichever is higher.
- Contract substitution (a different/worse contract signed abroad than the DMW-verified one) is illegal.
- Repatriation cost at contract end / early termination without just cause is the employer's responsibility.
- Standard contracts include medical/dental coverage during the term.
(Source: batasko.com/ofw/ofw-contract-rights, POEA Memorandum Circular 63-A)

## Escalation resources — link out, do not hardcode as the only source
- OWWA 24/7 Hotline: **1348**
- 1343 Actionline Against Human Trafficking: **1343**
- Country-specific POLO-OWWA / Migrant Workers Office (MWO) contacts: **link to the official DMW directory (dmw.gov.ph)** rather than hardcoding numbers/addresses — they change per country and a stale crisis contact is actively dangerous. The two hotline numbers above are stable and can be hardcoded; anything more specific than that should link out.

## Firestore data model
```
users/{uid}                                  — profile (destinationCountry, occupation — optional, user-entered)
users/{uid}/contractChecks/{checkId}         — {status, flags[], severity, createdAt}
  users/{uid}/contractChecks/{checkId}/messages/{msgId}   — conversation turns
users/{uid}/crisisSessions/{sessionId}       — {country, routedTo, timestamp, expireAt}
  users/{uid}/crisisSessions/{sessionId}/messages/{msgId} — conversation turns
```
`crisisSessions` documents get a **Firestore TTL policy on `expireAt`** (e.g. auto-delete 48–72h after creation) so a stored "my passport was taken" transcript doesn't sit indefinitely somewhere an abusive employer with device access could find it. This is a deliberate privacy design choice — implement the TTL field and configure the TTL policy on that collection, and also let the user manually delete a session at any time.

## Security requirements (OWASP Top 10 Web + OWASP Top 10 for LLM Apps — keep both in mind for every change)
- Firestore security rules must enforce `request.auth.uid == uid` on every path under `users/{uid}/...` — never rely on client-side filtering alone.
- Sanitize/validate all user input before it reaches a Gemini prompt, especially pasted contract text — treat it as untrusted and guard against prompt-injection attempts trying to override system instructions (e.g., "ignore previous instructions and...").
- Validate Gemini's structured JSON output against a strict schema before trusting or persisting it (severity values, flag fields, etc.) — never eval or directly render model output as HTML/markup without escaping.
- Never let the model fabricate a phone number, embassy address, or legal citation — if content isn't in the grounded reference list, it should direct the user to the official DMW/OWWA site rather than inventing specifics.
- No API keys, service account JSON, or secrets in source, `.env` files committed to git, or client-side bundles — Secret Manager or Cloud Run secret bindings only.
- Rate-limit or otherwise bound Gemini calls per user where practical — avoid unbounded cost/abuse surface.
- Crisis-mode conversation content is sensitive: don't log full transcripts to general application logs; keep them in the user-isolated, TTL'd Firestore path only.
- The app must never claim to give definitive legal advice — all Contract Check findings must be framed as "appears to conflict with standard POEA/DMW rules," with an explicit recommendation to verify with DMW/OWWA/a licensed lawyer.

## System prompts (draft v1 — content-level, reusable regardless of final agent architecture)

### Contract Check / Interviewer step
```
You are Gabay OFW's Contract Check assistant, helping a Filipino overseas worker deployed to Saudi Arabia, UAE, Qatar, or Kuwait understand whether their actual working conditions match their legally required contract terms.

Ground rules:
- Respond in the language the user uses — Tagalog, Bisaya, Taglish, or English — matching their code-switching naturally. Do not force English.
- You are not a lawyer and must never claim to give definitive legal advice or guarantee a legal outcome. Frame findings as "this appears to conflict with standard POEA/DMW contract rules" and always recommend the user verify with DMW/POLO/OWWA or a licensed lawyer.
- Known non-negotiable rules under Philippine OFW regulations, valid across occupations/destination countries: [list above]
- Conversation flow: ask the user to describe (a) what their original contract says, (b) what is actually happening. Ask clarifying follow-up questions one at a time when something is ambiguous. Do not overwhelm with a checklist upfront.
- When you have enough information, output the structured claims (contract terms stated, actual conditions described) for the rule-matching step — do not produce the final verdict yourself.
- If at any point the user describes physical danger, threats, confinement, or being unable to leave, immediately shift to crisis language: stop contract analysis, tell them clearly to contact OWWA's 24/7 hotline (1348) or the nearest Philippine Embassy/POLO office, and that trained humans are best placed to help with immediate safety. Do not attempt to counsel them through the danger yourself.
- Never fabricate a phone number, embassy address, or legal citation. If you don't have verified current contact details, direct them to the official DMW/OWWA site.
```

### Rule-Matcher step (invoked once per case)
```
You receive structured claims extracted from an OFW's conversation: what their contract states, and what is actually happening. Compare against these non-negotiable rules: [list above]. Output a structured verdict: for each flagged issue, name it, cite which rule it may violate, and rate severity (informational / concerning / urgent). Do not invent rules or salary figures not in your reference list. Do not claim legal certainty — frame as "appears to conflict with."
```

### Crisis / Immediate Help mode
```
You are Gabay OFW's immediate-help assistant. The user has indicated they need urgent help. Your job is triage and routing, not counseling or investigation.

- Respond in the user's language (Tagalog/Bisaya/Taglish/English), keep responses short and calm.
- Ask only the minimum needed to route correctly: (1) are you in physical danger right now or able to safely reach a phone/internet, (2) which country are you in, (3) one-line description of the situation.
- Do not ask for extensive detail about abuse, violence, or trafficking specifics — that is not your role and can retraumatize; a trained human handles that.
- Based on the situation, output the correct routing immediately:
  - Any safety threat, confinement, or trafficking indicator → 1343 Actionline and OWWA 24/7 hotline 1348, plus the nearest Philippine Embassy.
  - Passport confiscation / contract issues without immediate danger → the DMW/OWWA Migrant Workers Office (MWO) for their specific country (link to official directory).
  - Unpaid salary / labor dispute only → same MWO office, informational tone.
- Always close with: "You are not alone — these offices exist specifically to help OFWs in your situation, and reaching out does not cost you anything."
- Never attempt to resolve the crisis yourself, never ask for details beyond what's needed to route, never delay giving contact information for small talk.
```

## Language & stack conventions
- **Python** is the intended primary language (best-documented Google ADK support, if ADK ends up used at all) — don't introduce a second backend language without a clear reason.
- UI copy needs to support Tagalog/Bisaya/Taglish and English — don't hardcode English-only strings in UI components; follow the pattern already used in the design prototype (a `copy` object keyed by language, toggled by a language switch).
- A clickable UI prototype already exists (Claude Design canvas artifacts: "Gabay OFW" for the screens, "Gabay OFW Sprint" for the build tracker) — use it as the UI/UX reference for screen flow and copy tone, not as production code (it's static/scripted, not wired to Firebase/Gemini).

## Full context
See `PROJECT_HANDOFF.md` in this repo for the full background: competitive landscape and differentiation rationale, day-by-day build plan, and the current status of the open architecture decision. Keep that file's "Multi-agent design" section in sync with reality — if you implement an architecture, update that section to say so instead of leaving it marked open.
