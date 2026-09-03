# Gabay OFW

Gemini-powered app for Filipino Overseas Foreign Workers (OFWs) in the Gulf corridor (Saudi Arabia, UAE, Qatar, Kuwait), with two user-selected modes: Contract Check and Crisis Help.

## Language

### Modes

**Contract Check**:
The mode where a multi-turn conversation compares the user's actual working conditions against POEA/DMW standard employment contract rules, ending in a Findings Report.
_Avoid_: contract analysis, contract review

**Crisis Help**:
The mode that triages an urgent situation and routes the user to a real-world resource. Triage and routing only — never counseling through active danger.
_Avoid_: emergency mode, panic mode, SOS

**Mode**:
One of the two flows above, chosen explicitly by the user from the dashboard. Never inferred by an LLM from message content.

### Contract Check pipeline

**Interviewer**:
The LlmAgent that converses with the user to gather Claims. It asks clarifying questions one at a time and never produces the verdict itself.

**Rule-Matcher**:
The LlmAgent that receives complete Claims and produces the Findings Report. Runs exactly once per Contract Check.

**Claims**:
The structured JSON the Interviewer extracts from the conversation: topic-tagged pairs of what the contract states (`contract_says`) versus what is actually happening (`actually_happening`), plus a `status` completion signal. The handoff contract between Interviewer and Rule-Matcher.
_Avoid_: facts, summary, extraction

**Escalation**:
The Interviewer detecting danger (confinement, threats, physical danger) mid-Contract Check: the workflow ends with `status: escalate_to_crisis`, the UI shows hotlines plus a one-tap entry into Crisis Help carrying an Escalation Handoff. Never an automatic mode switch.

**Findings Report**:
The Rule-Matcher's structured verdict: per flagged issue, the issue name, the rule it appears to conflict with, and a Severity. Always framed as "appears to conflict with", never definitive legal advice.
_Avoid_: verdict, diagnosis, legal opinion

**Severity**:
One of `informational`, `concerning`, `urgent` — rated per flagged issue in the Findings Report.

### Crisis Help

**Routing**:
The Crisis Help outcome: which real-world resource the user is directed to. The agent outputs only a Triage Category; application code maps it to resources via a hardcoded table (1343 Actionline, OWWA hotline 1348, or the country's MWO via the official DMW directory), rendered by the UI outside the LLM text (see ADR-0002).

**Triage Category**:
The Crisis Help agent's structured classification of the situation: `safety_threat`, `trafficking_indicator`, `passport_confiscation`, `unpaid_wages`, or `other`. The only routing signal the LLM produces.

**MWO**:
Migrant Workers Office (formerly POLO-OWWA) — the country-specific DMW office. Contact details are always linked out to dmw.gov.ph, never hardcoded.

### Sessions

**Escalation Handoff**:
The minimal structured object carried from an escalated Contract Check into a new Crisis Session: country, reason category, a one-line summary in the user's language, and the source check ID. Never the conversation transcript. The Crisis Help agent opens by confirming it, not re-asking.

**Crisis Session**:
A stored Crisis Help conversation under `users/{uid}/crisisSessions/`, auto-deleted by Firestore TTL via its `expireAt` field and manually deletable by the user.

## v6 agent layer — Case pipeline

Terms for the PRD #34 / ADR-0004 DISPATCHER topology (`app/case.py`,
`app/agent.py`, `app/sequencer_agent.py`). These stand alongside, not in
place of, the Contract Check / Crisis Help terms above.

**Case**:
The structured facts DISPATCHER has built from the conversation, deterministically merged by `merge_case` and rendered back to the user in the UI, correctable in one tap (issue #44). Every claim carries provenance: `{value, source, confidence, at, conflicts[]}`. Stored as a plain JSON-serialisable dict in ADK session state.
_Avoid_: Claims (that name belongs to the retired Contract Check pipeline).

**Conflict**:
A first-class object on a Case claim, never a UI event — `claim["conflicts"]` accumulates `{value, source, confidence, at}` entries whenever a disagreeing value would otherwise silently overwrite one already on the claim: a user-confirmed value disagreeing with any later source, or two different non-user sources (extraction vs. document) disagreeing with each other. A document is frequently the fraud (a substituted contract), so it never automatically outranks her narrative — but her narrative doesn't silently overwrite a document already on file either. Resolved only by a `user`-sourced correction (the one-tap endpoint), which clears the list. An unresolved Conflict on a SequencerIn-mapped field (`country` or `tenure_months`; see `app.case.SEQUENCER_FIELDS`) blocks FILING_SEQUENCER and becomes the turn's one question; a Conflict elsewhere is informational only.

**Safety Flag**:
A named, closed-enum hazard on the Case (`PHYSICAL_ASSAULT_ONGOING`, `PHYSICAL_ASSAULT_PAST`, `THREAT_OF_HARM`, `CONFINED`, `PASSPORT_WITHHELD`). Add-only, outside Conflict precedence entirely: any source may add one, none may clear one — a document asserting "all is well" leaves every flag in place. Only an authenticated UI action clears (out of scope for the merge-policy slice).

**One-tap correction**:
The authenticated `POST /api/case/correct` endpoint: a `user`-sourced claim write that wins outright, sets `user_confirmed`, and resolves any Conflict on that field. Never an agent tool, never a conversation turn — the same house style as `mark_safe`/`panic_wipe`.

