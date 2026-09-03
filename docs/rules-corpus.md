# Rules corpus: sources, tiers, and enum derivation (issue #36)

The machine-readable corpus lives in `app/rules/`:

- `app/rules/schema.py` — pydantic schema; ADR-0005 tier bounds are
  enforced by validators (a Tier-2 row cannot carry a hard deadline or
  direct an irreversible action — it is unrepresentable, not discouraged).
- `app/rules/rows_qa.py` — Qatar rows (Tier-1, full strength).
- `app/rules/rows_sa.py` — Saudi rows (Tier-2 register throughout).
- `app/rules/__init__.py` — assembly, `JURISDICTION_STATUS`, and the
  selection function `rules_for(jurisdiction, grievance, tenure)`.
- `tests/test_rules_corpus.py` — the pure-function CI-gate suite.

`sequence_actions` / `verify_plan` consume `RuleRow` objects directly.
An empty `rules_for(...)` result means **no verified rule** — the caller
must route to the Safe Floor, never invent a step.

> **ADR reference note.** Issue #36 and PRD #34 cite ADR-0004 and
> ADR-0005. Those ADR files are not yet committed to `docs/adr/` (the
> repo currently holds ADR-0001..0003). This corpus implements the
> tier semantics as specified verbatim in PRD #34; when ADR-0005 lands,
> this document and `app/rules/schema.py` should be checked against it.

## Jurisdiction status

| Jurisdiction | Status | Rows |
|---|---|---|
| QA | ACTIVE | Tier-1 base; hard dates and full-strength directives allowed |
| SA | ACTIVE | Tier-2 register; protective/reversible steps only |
| KW | **HELD** | none — fixed refusal path |
| AE | **HELD** | none — fixed refusal path |

## Source list and tier classification

Tier bounds what a row may authorize, by reversibility (ADR-0005 per
PRD #34): Tier-1 = statute, official government guidance, or ILO material
published under an agreement with the government — may assert hard dates
and direct irreversible actions. Tier-2 = reputable NGO / ILO analysis —
protective reversible steps only, dates reported-not-relied-upon,
warnings at full strength.

### Qatar (rows ship Tier-1)

| Source | Tier | Why |
|---|---|---|
| Qatar Labour Law No. 14 of 2004, Art. 10 (Al Meezan portal) | 1 | Statute on the official legal portal. One-year limitation from the cause of action. |
| Law No. 13 of 2017, Art. 115 bis (Al Meezan) | 1 | Statute. MoL 7-day amicable settlement, Labour Dispute Settlement Committee decision within 3 weeks of first hearing. |
| ILO, *Know Your Rights — Qatar Labour Law* | 1 | ILO material under the ILO–Qatar technical cooperation programme (the PRD names this guide Tier-1 explicitly). Verified against the booklet text. |
| ILO, *Know Your Rights: a booklet for domestic workers in Qatar* | 1 | Same programme. Covers Law No. 15 of 2017 (Secs. 7, 12, 15, 17), Law No. 21 of 2015 Sec. 8(3) (passports), MOI Decision No. 95 of 2019 Art. 2 (exit; 72-hour notice). |

### Saudi Arabia (rows ship Tier-2 — deliberate downgrade)

Issue #36 expects Saudi rows at Tier-2. Where a row cites an official
Saudi source (Musaned, the 2023 Domestic Workers Regulation), the row
still ships at Tier-2: Amnesty documents systematic divergence between
Saudi official text and enforcement practice, so official assertions are
not relied on for anything irreversible. A row may downgrade its
source's tier (strictly more restrictive); the schema forbids the
opposite direction.

| Source | Source tier | Row tier | Why |
|---|---|---|---|
| Musaned Friendly Settlement (HRSD) | 1 | 2 | Official channel exists and is the filing venue; enforcement divergence documented by Amnesty, so no hard dates or irreversible directions ride on it. |
| Regulation for Domestic Workers (Council of Ministers 2023, HRSD PDF) | 1 | 2 | Same rationale. Grounds the passport-withholding and dispute-channel rows. |
| Amnesty International, *Once we step in their homes, we are no longer human* (2026, Filipino domestic workers) | 2 | 2 | Reputable NGO analysis. Grounds the huroob warning, the no-local-police warning, and the abuse-routing rows. |
| Amnesty International, *Locked in, Left Out* (2025, Kenyan domestic workers) | 2 | 2 | Corroborates the huroob system description. |
| Saudi Labor Law Art. 222 12-month limitation, as reported by practice guides | 2 | 2 | The statute text was not verified against the Official Gazette; the deadline therefore ships as a `ReportedDeadline` (reported-not-relied-upon, confirm with the MWO), never a countdown. |
| 90-day non-withdrawal rule (labor-court procedural practice reported by Saudi legal practice guides and Philippine MWO advisories) | 2 | 2 (warning-only) | **Warning-only content, never a step.** ADR-0005 ships warnings at full strength at Tier-2 because the failure direction is safe: being wrong about it only makes her more careful (PRD user story 8). Issue #36 mandates this warning ship unhedged. |

## Grievance enum derivation

Values exist only because sourced rows branch on them. The test
`test_grievance_values_actually_distinguish_rows` enforces that no two
values give identical guidance in every cell they share.

| Value | Forced by | Distinction it carries |
|---|---|---|
| `UNPAID_WAGES` | QA Art. 10 + Art. 115 bis rows; SA Musaned rows | The only grievance with a limitation deadline (hard 1 year in QA; reported 12 months in SA). Covers wages **and** end-of-service money claims — in every sourced row they share venue, timing, and deadline, so a separate EOSB value would be invented granularity. |
| `PASSPORT_WITHHELD` | QA Law No. 21 of 2015 Sec. 8(3) row; SA 2023 Regulation row | No limitation deadline (ongoing violation); QA carries the QAR 25,000 fine fact; recovery routes through the complaint, not the employer. |
| `PHYSICAL_ABUSE_OR_DANGER` | QA Law No. 15 of 2017 Sec. 17 rows; SA Amnesty-grounded rows | Adds the safety-first venue change (SA: MWO before any filing; QA: no-notice termination right that preserves EOSB). SA rows carry the no-local-police warning. |
| `STATUS_RETALIATION` | QA QID-cancellation procedure (ILO guide / Decree-Law 18/2020); SA huroob contest row | A distinct procedure in each jurisdiction (QA: complaint then signed Arabic letter to the Head of the Labour Relations Department; SA: MWO-assisted contest through HRSD/Absher). |
| `EXIT_BLOCKED` | QA MOI Decision No. 95 of 2019 row; SA final-exit confirm-first row | The before/after-leaving core: QA asserts the right to leave (no exit permit, 72-hour notice); SA is confirm-first only — reported employer-objection window, reported case-blocks-exit interaction, never a countdown. |

Grievances deliberately **not** in the enum: contract substitution /
employer breach (its sourced handling — file the same MoL complaint,
same venue, same one-year deadline — is field-identical to
`UNPAID_WAGES` rows, so a separate value would distinguish nothing) and
anything for KW/AE.

## Tenure bucket derivation

"Tenure situation" per issue #36 is position relative to employer and
country — the axis the sourced rows actually branch on. The test
`test_tenure_buckets_actually_distinguish_rows` enforces each pair of
buckets differs somewhere.

| Bucket | Forced by |
|---|---|
| `EMPLOYED_IN_COUNTRY` | Baseline filing rows in both jurisdictions. |
| `LEFT_EMPLOYER_IN_COUNTRY` | SA rows add the huroob counter-report warning the moment she leaves the employer (Amnesty); QA rows add the no-notice job-change path on employer breach (Decree-Law 18/2020). Filing order versus flight is decided in this bucket. |
| `DEPARTED_COUNTRY` | Venue changes: QA money claims proceed via the MoL online platform or a representative under the still-running Art. 10 clock; SA claims route via the MWO/DMW with a confirm-first note. Only money claims have sourced post-departure rows — other cells are intentionally empty (no sourced guidance → Safe Floor). |

Deliberately **not** buckets: length-of-service distinctions (probation,
one-year EOSB vesting, 2-year notice tiers). They change entitlement
amounts and notice arithmetic, not where/when to file or the deadline —
bucketing on them would be invented granularity.

## Intentional coverage gaps

The corpus is not a full matrix. A cell with no row means no sourced
guidance exists for it, and `rules_for` returns `()` — the sequencer
must fall back to the Safe Floor. Current intentional gaps: post-departure
rows for passport/abuse/status/exit grievances (either moot after
departure or unsourced), and SA `STATUS_RETALIATION` outside the
left-employer bucket (huroob reports are made against workers who have
left).
