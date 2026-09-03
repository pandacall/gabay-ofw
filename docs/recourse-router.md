# RECOURSE_ROUTER: sources, forks, and executor derivation (issue #48)

The machine-readable route table lives in `app/recourse/`:

- `app/recourse/schema.py` — typed boundary: `RecourseRouteIn` (the
  closed-enum input — country, tenure, grievances, agency, and the
  optional `family_region` attribute), `RecourseRoute` (the design
  session's output shape, verbatim), `RecourseRouterOut`.
- `app/recourse/routes.py` — the pure route-table function
  (`build_recourse_routes`), its citations, and the AKSYON Fund tier
  classifier.
- `app/recourse/agent.py` — the single-turn agent wiring.
- `tests/test_recourse_routes.py` — the pure-function CI-gate suite.
- `tests/test_recourse_agent.py` — tool-wrapper and HTTP-seam tests.

> **ADR reference note** (mirrors `docs/rules-corpus.md`'s own note).
> Issue #48 and PRD #34 cite ADR-0004 (topology) and ADR-0005 (source
> tiers). Those ADR files are not yet committed to `docs/adr/` (the repo
> currently holds ADR-0001..0003, 0006, 0007) — this module implements
> the topology and tier semantics exactly as specified verbatim in PRD
> #34; when ADR-0004/0005 land, this module should be checked against
> them.

## Forks, in the order `build_recourse_routes` checks them

1. **Already out of the house** (`tenure is LEFT_EMPLOYER_IN_COUNTRY`):
   she has left her employer's household but is still in the host
   country. The only route this bucket opens is OWWA/MWO-assisted
   repatriation — never a filing route (issue #48's repatriation-track
   fixture: "routes OWWA, not filing"). This is a genuine interpretation
   call recorded here for reviewers: `DEPARTED_COUNTRY` is a different
   bucket (she is already home, so repatriation does not apply — the
   license fork runs for her instead); `EMPLOYED_IN_COUNTRY` is
   unaffected.
2. **Agency license fork** (reuses `check_agency_license` /
   `is_wrong_venue` from `app.complaint.agency`, issue #46 — never
   re-derived): a confirmed `LICENSED` match clears SEnA plus the RA
   8042/10022 joint-and-solidary liability lever against the same
   agency. Every other status (`DIRECT_HIRE`, `NOT_FOUND`, `DELISTED`,
   `CANCELLED`, `EXPIRED`) forks to the illegal-recruitment criminal
   track instead — SEnA is a labor money-claims venue, not a criminal
   one, so it is absent entirely from this fork, never offered
   alongside the wrong-venue route.
3. **AKSYON Fund** (additive, rides alongside whichever fork above
   fired, whenever at least one grievance was reported): tier by case
   classification per D.O. No. 5 s.2024. The higher (PHP 75,000) tier
   requires a severity fact (severe illness, injury, or abuse-caused
   disability) that `RecourseRouteIn` does not carry — it has a
   grievance *category* (`PHYSICAL_ABUSE_OR_DANGER`), not an injury
   *outcome*. Abuse, exploitation, illegal recruitment, and contract
   violations are themselves the PHP 50,000 (base) tier per the fund's
   own published breakdown, so every grievance this corpus covers today
   classifies to the base tier — never guessed up to the higher tier
   without the fact that actually authorizes it (fail closed).

## Source list and tier classification

All Tier-1: statute text verified against the official legislative
repository (Lawphil), or an official government department/board
channel (NCMB, DMW) — ADR-0005 per PRD #34.

| Source | Tier | Grounds |
|---|---|---|
| NCMB/DOLE Single Entry Approach (SEnA) — online/abroad filing (Republic Act No. 10396) | 1 | The SEnA route's venue and its "filable from abroad" claim: filed online via the NCMB/DOLE e-SEnA (ARMS) portal, endorsed through the MWO/POLO abroad, or filed by a family member holding a Special Power of Attorney (SPA). |
| Republic Act No. 8042, Sec. 10 (Money Claims), as amended by Republic Act No. 10022, Sec. 7 | 1 | The joint-and-solidary liability lever: "the liability of the principal/employer and the recruitment/placement agency for any and all claims under this section shall be joint and several", answerable via the agency's performance bond. |
| Republic Act No. 8042, Sec. 6 (Illegal Recruitment), as amended by Republic Act No. 10022, Sec. 5 | 1 | The illegal-recruitment fork's venue and criminal basis: deployment through an unlicensed agency or an unlicensed direct hire is illegal recruitment; the statute lets "the Secretary of Labor and Employment, the [DMW] Administrator or their duly authorized representatives, or any aggrieved person" initiate the complaint, prosecuted with the anti-illegal-recruitment branch. |
| DMW One Repatriation Command Center (ORCC) / MWO repatriation assistance | 1 | The already-out-of-the-house fork's venue: MWO/POLO abroad, or DMW's ORCC in Manila (the same national command center `app/directory.py`'s `dmw_orcc` entry already resolves — this module names it without repeating its phone number, per the immutable-directory house rule). |
| DMW AKSYON Fund (Department Order No. 5, Series of 2024) | 1 | The AKSYON Fund route's venue, tiers, and one-year filing window: financial/legal assistance for distressed OFWs (abuse, exploitation, illegal recruitment, contract violations at PHP 50,000; severe illness or injury at PHP 75,000), filed at the MWO if abroad or DMW if already in the Philippines. |

## Executor derivation ("pin down concretely how each route executes from abroad")

Every route in this table ships `executor: EITHER` — not by default, but
because every sourced path this corpus currently covers has a real door
on both sides:

- **SEnA**: the worker herself may file through the MWO/POLO in her host
  country or DOLE's ARMS e-SEnA online portal (`SELF` is real here, per
  PRD #48); a family member may instead walk it in under a Special Power
  of Attorney (`KIN`).
- **Solidary-liability lever**: rides on the same SEnA/NLRC process, so
  the same two doors apply.
- **Illegal recruitment**: RA 8042 Sec. 6 itself lets "any aggrieved
  person" initiate the complaint, and DMW's own published guidance
  accepts an online/emailed report (worker) or an SPA-authorized
  representative walking it in (family).
- **OWWA repatriation**: the MWO/POLO abroad can be reached by the
  worker herself; DMW's ORCC in Manila can be reached by her family.
- **AKSYON Fund**: filed at the MWO if she is still abroad, or at DMW if
  already in the Philippines (a family member may submit on her
  behalf).

A future route sourced with only one real executable side should ship
that narrower value (`SELF` or `KIN` alone) — `EITHER` is a property of
what is sourced today, never a default.

## Regional-office fork ("never Manila-centric")

`family_region` (`FamilyRegion.METRO_MANILA` /
`FamilyRegion.OUTSIDE_METRO_MANILA`, optional — `None` means DISPATCHER
never asked) decides the geographic qualifier a PH-side venue is named
with, via `_regional_descriptor`: "the regional/satellite office nearest
your family" when set to outside Metro Manila, "the NCR office" when set
to Metro Manila, and a generic "the office serving your family's
location" when unset — never assuming Metro Manila by default. This
qualifier only supplies the "where" half of a venue; each route names
its OWN institution explicitly (the NCMB/DOLE SEnA desk, the NLRC
Regional Arbitration Branch, the DMW anti-illegal-recruitment branch, or
DMW for AKSYON Fund) rather than blending distinct agencies into one
interchangeable phrase — DMW, DOLE/NCMB, and NLRC each maintain their
own regional office network, so "the regional office" is never
institution-agnostic. No route in this table
carries a phone number: contact numbers render only via `office_directory`
/ `action_card` (the immutable directory) or a `dmw.gov.ph` link-out, per
house rules.
