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
