# DEBUNKER claim-template corpus — sourcing derivation (issue #47)

The corpus lives in `app/debunker_corpus.py`. This document records how
each entry was derived, mirroring `docs/rules-corpus.md`. The PRD (#34)
tracks the two research tasks separately, and so does the data:

- **Claim sourcing** (`heard_from`): evidence that workers are actually
  told this. The claim list is what she hears, not what we imagine.
- **Rebuttal sourcing** (`citations`): what makes the verdict true, with
  a Source Tier per ADR-0005.

## Why a deterministic classifier

`search_corpus` classifies over this closed set with normalization plus
hand-written stem groups — no embeddings. That removes the
vector-poisoning surface entirely (nothing an adversary writes can move a
claim's neighborhood) and makes refusal fixture-testable: an unknown
claim yields NOT_COVERED, always, and CI proves it
(`tests/test_debunker_classifier.py`).

## Register per tier (ADR-0005)

The register lives in the rebuttal text itself, so rendering is
deterministic:

- **Tier-1** asserts flatly ("You owe no placement fee.").
- **Tier-2** names its source and states its limit ("as reported by …;
  not confirmed here against the statute text — the MWO can confirm").

Structural validators make a Tier-1 entry resting on a sub-Tier-1
citation, or a Tier-2 rebuttal that fails to route to the MWO,
unrepresentable.

## The templates

| template_id | The claim (as told) | Heard from | Verdict | Rebuttal source | Tier | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `cannot_leave_until_repaid` | "You can't leave until you repay" | Amnesty PH 2026 testimonies | FALSE | 2016 Revised POEA Rules, Rule V §51 (no placement fee for domestic workers) | 1 | The rebuttal removes the debt premise; the leave-safely caution routes through the MWO without hedging the verdict. |
| `placement_fee_debt` | "Utang mo ang placement fee" | Amnesty PH 2026 testimonies | FALSE | 2016 Revised POEA Rules, Rule V §51; no-fee policy since POEA GBR 06 s. 2006 | 1 | Domestic workers owe zero placement fee under DMW rules; charging one is illegal recruitment. |
| `passport_withholding_legal` | "Passport withholding is legal" | Amnesty PH 2026 testimonies | FALSE | ILO KYR booklet for domestic workers in Qatar (Law 21/2015 §8(3)); SA Regulation for Domestic Workers (2023) | 1 | Both active jurisdictions prohibit it; both citations are Tier-1. |
| `noc_required_qatar` | "You need an NOC" | ILO KYR Qatar guide (answers the myth directly) | FALSE | ILO KYR Qatar (Decree-Law No. 18 of 2020 abolished the NOC) | 1 | False in Qatar — the entry carries `applies_in=("QA",)`: for any other (or unknown) country a matched NOC claim fails closed to NOT_COVERED and routes to the MWO instead of asserting. |
| `two_year_lock_in` | "You must complete two years" | Amnesty PH 2026 testimonies | FALSE | ILO KYR booklet for domestic workers in Qatar (§§12, 17) | **2 (deliberate downgrade)** | Tier-1 for Qatar, but the rebuttal generalizes to SA on MWO-advisory reporting, so the entry ships at Tier-2: an entry may downgrade its source's tier, never upgrade it. |
| `sa_ninety_day_withdrawal` | "Withdraw and you can't refile for 90 days" | MWO orientation advisories | TRUE | Saudi labor-court practice as reported (same citation as `app/rules/rows_sa.py`) | 2 | The one TRUE entry: confirming a true warning at full strength matters as much as debunking a lie (PRD story 8). No Case write — only FALSE plan-relevant verdicts write. |

## Classification precedence

Template order in `CLAIM_TEMPLATES` is precedence; the first match wins.
`cannot_leave_until_repaid` is listed before `placement_fee_debt` so a
combined claim ("hindi ako pwedeng umuwi hangga't may utang ako sa
placement fee") resolves to the more movement-restricting belief.

## Matching rules

Normalization: lowercase, diacritics stripped, punctuation to spaces.
Stems then match by three deterministic rules (see
`app.debunker._stem_matches`): multi-word stems match at a word-boundary
prefix ("two year" matches "two years"); short/numeric stems match exact
tokens only ("noc" never matches inside another word); other stems match
as token substrings so Tagalog inflection is covered ("bayar" matches
"nababayaran").

## NOT_COVERED routes, never shrugs

An unknown claim returns the fixed routing message — "I can't verify
that; the MWO can, here's the number" — the same shape as the Safe
Floor. The routing rows come from the immutable directory
(`app/directory.py`, issue #39): channel-tagged, dialability-filtered
for her country (a number she cannot dial from where she is ships only
as a Manila-relay row), with MWO contacts resolved from the official DMW
directory. Any number in the message is interpolated from those rows,
never generated, and the rows cross ROUTING_GUARD again on the way back
(both `DEBUNKER` and `search_corpus` are on the guard's allowlist; the
DEBUNKER agent also carries the guard's second-rail before-tool
callback). The HTTP-seam test (`tests/test_debunker_http.py`) asserts
the routing rows equal the directory rows for her country.

## Case write on FALSE

A FALSE verdict on a plan-relevant belief merges
`debunked_<template_id> = {value: "FALSE", source: "debunker",
confidence, at}` into the Case via `merge_case` — provenance included so
a later Plan resting on the belief goes stale via the input-hash
mechanism (issue #43). User-confirmed values are never reverted; a
disagreement becomes a Conflict per the merge policy.
