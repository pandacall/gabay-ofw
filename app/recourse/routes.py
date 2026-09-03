"""RECOURSE_ROUTER's route table: pure functions, no model, no I/O
(issue #48, PRD #34).

Reuses ``check_agency_license``/``is_wrong_venue`` from
:mod:`app.complaint.agency` — the DMW licensed-agency fixture lookup
COMPLAINT_DRAFTER already built (issue #46) — rather than duplicating it;
this module is a second consumer of that same correctness gate, exactly
as PRD #34 describes it ("a correctness dependency of COMPLAINT_DRAFTER").

Three forks, in the order they are checked:

1. **Already out of the house** (``tenure is LEFT_EMPLOYER_IN_COUNTRY``):
   she has left her employer's household but is still in the host
   country — the sourced route here is OWWA/MWO-assisted repatriation,
   not a filing venue (issue #48's repatriation-track fixture: "routes
   OWWA, not filing"). No SEnA, no illegal-recruitment route, no Aksyon
   Fund route rides alongside it: getting her home safely is the only
   door this module opens while she is in this bucket. (``DEPARTED_
   COUNTRY`` is a different bucket — she is already home, so repatriation
   does not apply; the license fork below runs for her instead.)
2. **Agency license fork** (``check_agency_license``): a confirmed
   LICENSED agency clears SEnA, plus the RA 8042/10022 joint-and-solidary
   liability lever against the same agency; anything else (DIRECT_HIRE,
   NOT_FOUND, DELISTED, CANCELLED, EXPIRED) forks away from SEnA
   entirely into the illegal-recruitment criminal-complaint track — SEnA
   is a labor money-claims venue, not a criminal one, and naming the
   wrong venue first wastes her one shot at a working filing order.
3. **AKSYON Fund** (DMW Department Order No. 5, s. 2024): rides alongside
   whichever fork above fired, whenever at least one grievance was
   reported — it is a support-and-legal-aid grant, not a competing legal
   venue, so it is additive rather than exclusive. Tier follows case
   classification per the fund's own published breakdown: abuse,
   exploitation, illegal recruitment, and contract violations are the
   base tier (PHP 50,000); the higher "severe injury" tier (PHP 75,000)
   requires a severity fact (severe illness, injury, or abuse-caused
   disability) that :class:`~app.recourse.schema.RecourseRouteIn` does
   not carry — so every grievance this corpus covers today classifies
   to the base tier, never guessed up (fail closed) — see
   :data:`AksyonFundTier` and :func:`_aksyon_tier`.

Every route's ``executor`` is decided by what is actually sourced for
that route to be executed from abroad (PRD #48: "pin down concretely how
each route executes from abroad, with source"):

- SEnA (:data:`CIT_SENA_ABROAD`): the worker herself may file through the
  MWO/POLO in her host country, DOLE's ARMS e-SEnA online portal, or
  authorize a Special Power of Attorney (SPA) representative — ``SELF``
  is real here, so the route ships ``EITHER``.
- The RA 8042/10022 solidary-liability lever rides on the same SEnA/NLRC
  process, so it ships ``EITHER`` too.
- Illegal recruitment (RA 8042 Sec. 6, as amended by RA 10022 Sec. 5):
  the statute itself lets "any aggrieved person" initiate the complaint,
  and DMW's own guidance accepts an online/emailed report or an SPA
  representative walking it in — ``EITHER``.
- OWWA repatriation: the MWO/POLO abroad can be reached by the worker
  herself, and DMW's ORCC in Manila can be reached by her family —
  ``EITHER``.
- AKSYON Fund: filed at the MWO if she is still abroad, or at DMW if
  already in the Philippines (family may submit on her behalf) —
  ``EITHER``.

No route in this table ships bare ``SELF`` or bare ``KIN``: every sourced
path this corpus currently covers has a real door on both sides. A
future route with only one real executable side should ship that
narrower value — this is a property of what is sourced, not a rule that
forces ``EITHER``.

Regional-office naming (issue #48's regional-office fixture): a PH-side
venue never assumes Metro Manila. When ``family_region`` is
``OUTSIDE_METRO_MANILA``, the venue names the regional/satellite DMW or
NCMB office nearest the family instead of a Metro Manila office; when it
is ``METRO_MANILA`` or unset (``None`` — never asked), the venue names
the NCR-based office. DMW's own office network is genuinely split this
way (an NCR office plus separate regional/satellite offices), so this
is not invented granularity.
"""

from __future__ import annotations

from enum import Enum

from app.complaint.agency import check_agency_license, is_wrong_venue
from app.recourse.schema import (
    Executor,
    FamilyRegion,
    RecourseRoute,
    RecourseRouteIn,
)
from app.rules.schema import Citation, SourceTier, TenureBucket

# ---------------------------------------------------------------------------
# Sources (Tier-1 throughout: statute text verified against the official
# legislative repository, or an official government department/board
# channel — ADR-0005 per PRD #34).
# ---------------------------------------------------------------------------

CIT_SENA_ABROAD = Citation(
    source_name="NCMB / DOLE Single Entry Approach (SEnA) — online and abroad filing",
    reference=(
        "SEnA Request for Assistance may be filed online through the "
        "NCMB/DOLE e-SEnA (ARMS) portal, endorsed through the MWO/POLO in "
        "the host country, or filed by an immediate family member holding "
        "a Special Power of Attorney (SPA) — a 30-day mandatory "
        "conciliation-mediation period follows (Republic Act No. 10396)"
    ),
    url="https://ncmb.gov.ph/single-entry-approach-sena/",
    tier=SourceTier.TIER_1,
)

CIT_RA8042_SEC10_SOLIDARY = Citation(
    source_name=(
        "Republic Act No. 8042, Sec. 10 (Money Claims), as amended by "
        "Republic Act No. 10022, Sec. 7"
    ),
    reference=(
        "\"The liability of the principal/employer and the recruitment/"
        "placement agency for any and all claims under this section "
        "shall be joint and several\" — the licensed agency answers in "
        "full for the foreign employer's money claim, via its performance "
        "bond, before the NLRC"
    ),
    url="https://lawphil.net/statutes/repacts/ra2010/ra_10022_2010.html",
    tier=SourceTier.TIER_1,
)

CIT_RA8042_SEC6_ILLEGAL_RECRUITMENT = Citation(
    source_name=(
        "Republic Act No. 8042, Sec. 6 (Illegal Recruitment), as amended "
        "by Republic Act No. 10022, Sec. 5"
    ),
    reference=(
        "Deployment through an unlicensed agency, or direct hire for "
        "household work abroad without a license, is illegal recruitment "
        "— a criminal matter the Secretary of Labor, the DMW "
        "Administrator, their authorized representatives, \"or any "
        "aggrieved person\" may initiate with the appropriate office; "
        "prosecuted with the DMW's anti-illegal-recruitment branch"
    ),
    url="https://lawphil.net/statutes/repacts/ra2010/ra_10022_2010.html",
    tier=SourceTier.TIER_1,
)

CIT_OWWA_REPATRIATION = Citation(
    source_name="DMW One Repatriation Command Center (ORCC) / MWO repatriation assistance",
    reference=(
        "A worker who has left her employer's household while still in "
        "the host country is assisted home through the MWO/POLO abroad "
        "or DMW's ORCC in Manila — repatriation, not a filing venue, is "
        "the door this bucket opens"
    ),
    url="https://dmw.gov.ph/",
    tier=SourceTier.TIER_1,
)

CIT_AKSYON_FUND = Citation(
    source_name="DMW AKSYON Fund (Department Order No. 5, Series of 2024)",
    reference=(
        "Financial, medical, and legal assistance for distressed OFWs — "
        "PHP 50,000 for abuse, exploitation, illegal recruitment, or "
        "contract-violation cases; PHP 75,000 for severe illness or "
        "injury (including abuse-caused disability); filed at the MWO if "
        "still abroad or at DMW if already in the Philippines, within one "
        "year of the qualifying event"
    ),
    url="https://dmw.gov.ph/archives/v1/issuances/department-orders",
    tier=SourceTier.TIER_1,
)


class AksyonFundTier(str, Enum):
    """AKSYON Fund grant tier by case classification (D.O. No. 5 s.2024)."""

    #: Abuse, exploitation, illegal recruitment, or contract violations.
    BASE = "php_50000"
    #: Severe illness or injury, including abuse-caused disability.
    SEVERE_INJURY = "php_75000"


def _regional_descriptor(family_region: FamilyRegion | None) -> str:
    """The geographic qualifier a PH-side venue is named with — never
    Metro Manila by default (issue #48's regional-office fixture). Each
    route names its OWN institution explicitly (NCMB, NLRC, DMW); this
    only supplies the "where" half, never the institution itself, so
    distinct agencies are never blended into one interchangeable phrase.
    """
    if family_region is FamilyRegion.OUTSIDE_METRO_MANILA:
        return "the regional/satellite office nearest your family"
    if family_region is FamilyRegion.METRO_MANILA:
        return "the NCR office"
    # Never asked: name it generically, never assume Metro Manila.
    return "the office serving your family's location"


def _sena_route(country: str, family_region: FamilyRegion | None) -> RecourseRoute:
    return RecourseRoute(
        venue=(
            f"DOLE Single Entry Approach (SEnA) — online via DOLE ARMS "
            f"(e-SEnA), through the MWO/POLO in {country}, or in person "
            f"at the NCMB/DOLE SEnA desk — {_regional_descriptor(family_region)}"
        ),
        prerequisites=(
            "Employment contract or other proof of the employer-employee "
            "relationship",
        ),
        executor=Executor.EITHER,
        what_to_bring=(
            "Valid ID",
            "Employment contract, payslips, or other proof of employment",
            "Special Power of Attorney (SPA), if a family member files on "
            "her behalf",
        ),
        source=CIT_SENA_ABROAD,
    )


def _solidary_liability_route(family_region: FamilyRegion | None) -> RecourseRoute:
    return RecourseRoute(
        venue=(
            f"NLRC Regional Arbitration Branch money claim (after SEnA "
            f"conciliation-mediation) naming the licensed "
            f"recruitment/placement agency jointly and severally liable "
            f"with the foreign employer — {_regional_descriptor(family_region)}"
        ),
        prerequisites=(
            "SEnA conciliation-mediation attempted (Republic Act No. "
            "10396) — a 30-day mandatory step before NLRC",
        ),
        executor=Executor.EITHER,
        what_to_bring=(
            "Employment contract naming the recruitment/placement agency",
            "Evidence of the money claim (unpaid wages, unremitted "
            "benefits, unexpired-contract salary)",
        ),
        source=CIT_RA8042_SEC10_SOLIDARY,
    )


def _illegal_recruitment_route(family_region: FamilyRegion | None) -> RecourseRoute:
    return RecourseRoute(
        venue=(
            f"DMW anti-illegal-recruitment branch (criminal "
            f"Affidavit-Complaint) — online/email report, or in person at "
            f"{_regional_descriptor(family_region)}"
        ),
        prerequisites=(
            "Sworn/notarized Affidavit-Complaint narrating the recruitment",
        ),
        executor=Executor.EITHER,
        what_to_bring=(
            "Receipts, contracts, or chat/payment records with the agency "
            "or the direct-hire employer",
            "Passport biodata page",
            "Special Power of Attorney (SPA), if a family member files on "
            "her behalf",
        ),
        source=CIT_RA8042_SEC6_ILLEGAL_RECRUITMENT,
    )


def _owwa_repatriation_route() -> RecourseRoute:
    return RecourseRoute(
        venue=(
            "OWWA/MWO-assisted repatriation — through the MWO/POLO abroad, "
            "or DMW's One Repatriation Command Center (ORCC) in Manila if "
            "your family reports it"
        ),
        prerequisites=(),
        executor=Executor.EITHER,
        what_to_bring=("Passport, if still in her possession",),
        source=CIT_OWWA_REPATRIATION,
    )


def _aksyon_tier() -> AksyonFundTier:
    """Case classification per D.O. No. 5 s.2024.

    The higher (PHP 75,000) tier is reserved for a *severe* illness,
    injury, or abuse-caused disability — a severity fact
    :class:`~app.recourse.schema.RecourseRouteIn` does not carry (it has
    a grievance category, ``PHYSICAL_ABUSE_OR_DANGER``, not an injury
    outcome). Abuse, exploitation, illegal recruitment, and contract
    violations are themselves the PHP 50,000 (base) tier per the fund's
    own published breakdown (see :data:`CIT_AKSYON_FUND`) — so every
    grievance this corpus covers today classifies to the base tier,
    never guessed up to the severe-injury tier without the fact that
    actually authorizes it (the same fail-closed posture as
    ``check_agency_license``'s NOT_FOUND: never assert what is not
    confirmed). Takes no arguments deliberately: there is currently no
    typed signal that could change the answer.
    """
    return AksyonFundTier.BASE


def _aksyon_fund_route(family_region: FamilyRegion | None) -> RecourseRoute:
    tier = _aksyon_tier()
    amount = "PHP 75,000" if tier is AksyonFundTier.SEVERE_INJURY else "PHP 50,000"
    return RecourseRoute(
        venue=(
            f"DMW AKSYON Fund financial/legal assistance ({amount} tier) "
            f"— submitted to the MWO if still abroad, or to DMW at "
            f"{_regional_descriptor(family_region)} if already in the "
            f"Philippines"
        ),
        prerequisites=(
            "Filed within one year of the qualifying event (e.g. the "
            "abuse, the illegal recruitment, or arrival in the "
            "Philippines)",
        ),
        executor=Executor.EITHER,
        what_to_bring=(
            "Valid ID",
            "Supporting evidence for the qualifying case (e.g. a medical "
            "report, an MWO/police blotter, the employment contract)",
        ),
        source=CIT_AKSYON_FUND,
    )


def build_recourse_routes(route_in: RecourseRouteIn) -> tuple[RecourseRoute, ...]:
    """Every open door for one worker situation, in fork order.

    Pure: no I/O, no randomness, no model. Reuses ``check_agency_license``
    (issue #46) rather than re-deriving license status.
    """
    country = route_in.country.value

    if route_in.tenure is TenureBucket.LEFT_EMPLOYER_IN_COUNTRY:
        # Already out of the house: repatriation, not filing (issue #48's
        # repatriation-track fixture). No SEnA, no illegal-recruitment
        # route, no Aksyon Fund route rides alongside it.
        return (_owwa_repatriation_route(),)

    result = check_agency_license(
        route_in.agency.name, direct_hire=route_in.agency.direct_hire
    )
    licensed = not is_wrong_venue(result)

    routes: list[RecourseRoute] = []
    if licensed:
        routes.append(_sena_route(country, route_in.family_region))
        routes.append(_solidary_liability_route(route_in.family_region))
    else:
        routes.append(_illegal_recruitment_route(route_in.family_region))

    if route_in.grievances:
        routes.append(_aksyon_fund_route(route_in.family_region))

    return tuple(routes)
