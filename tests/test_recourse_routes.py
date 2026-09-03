"""RECOURSE_ROUTER's route table: CI-gating pure-function suite (issue
#48, PRD #34). No model, no I/O — every fork is exercised directly
against :func:`build_recourse_routes`.
"""

from __future__ import annotations

from app.complaint.schema import AgencyInfo
from app.recourse.routes import (
    AksyonFundTier,
    _aksyon_tier,
    build_recourse_routes,
)
from app.recourse.schema import (
    Executor,
    FamilyRegion,
    RecourseRouteIn,
)
from app.rules.schema import Grievance, Jurisdiction, SourceTier, TenureBucket

LICENSED_AGENCY = AgencyInfo(name="Sample Overseas Manpower Services, Inc.")
UNLICENSED_AGENCY = AgencyInfo(name="Placeholder Global Recruitment Corp.")
UNKNOWN_AGENCY = AgencyInfo(name="Totally Made Up Agency Name Ltd.")
DIRECT_HIRE = AgencyInfo(direct_hire=True)


def _route_in(**overrides) -> RecourseRouteIn:
    defaults = dict(
        country=Jurisdiction.SA,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        grievances=(Grievance.UNPAID_WAGES,),
        agency=LICENSED_AGENCY,
        family_region=None,
    )
    defaults.update(overrides)
    return RecourseRouteIn(**defaults)


class TestLicenseFork:
    """Acceptance: licensed -> SEnA + solidary lever; unlicensed ->
    illegal-recruitment track, SEnA absent."""

    def test_licensed_agency_gets_sena_and_solidary_lever(self):
        routes = build_recourse_routes(_route_in(agency=LICENSED_AGENCY))
        venues = [r.venue for r in routes]
        assert any("Single Entry Approach" in v or "SEnA" in v for v in venues)
        assert any("jointly and severally liable" in v for v in venues)
        assert not any("illegal-recruitment" in v.lower() for v in venues)

    def test_unlicensed_agency_gets_illegal_recruitment_no_sena(self):
        routes = build_recourse_routes(_route_in(agency=UNLICENSED_AGENCY))
        venues = [r.venue for r in routes]
        assert any("anti-illegal-recruitment" in v for v in venues)
        # SEnA is absent entirely — never the wrong venue alongside the
        # right one.
        assert not any("Single Entry Approach" in v for v in venues)
        assert not any("jointly and severally liable" in v for v in venues)

    def test_direct_hire_gets_illegal_recruitment_no_sena(self):
        routes = build_recourse_routes(_route_in(agency=DIRECT_HIRE))
        venues = [r.venue for r in routes]
        assert any("anti-illegal-recruitment" in v for v in venues)
        assert not any("Single Entry Approach" in v for v in venues)

    def test_unknown_agency_name_fails_closed_to_illegal_recruitment(self):
        # NOT_FOUND is not "assumed licensed" (same fail-closed posture as
        # check_agency_license itself).
        routes = build_recourse_routes(_route_in(agency=UNKNOWN_AGENCY))
        venues = [r.venue for r in routes]
        assert any("anti-illegal-recruitment" in v for v in venues)
        assert not any("Single Entry Approach" in v for v in venues)

    def test_every_licensed_route_names_venue_executor_prerequisites_source(self):
        routes = build_recourse_routes(_route_in(agency=LICENSED_AGENCY))
        for route in routes:
            assert route.venue
            assert route.executor in Executor
            assert isinstance(route.prerequisites, tuple)
            assert route.source.tier is SourceTier.TIER_1

    def test_sena_executor_is_either_self_is_real_from_abroad(self):
        (sena_route, *_rest) = build_recourse_routes(
            _route_in(agency=LICENSED_AGENCY)
        )
        assert sena_route.executor is Executor.EITHER
        assert "MWO" in sena_route.venue or "ARMS" in sena_route.venue


class TestRepatriationTrack:
    """Acceptance: already-out case routes OWWA, not filing."""

    def test_already_out_of_the_house_routes_owwa_only(self):
        routes = build_recourse_routes(
            _route_in(tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY)
        )
        assert len(routes) == 1
        (route,) = routes
        assert "OWWA" in route.venue or "repatriation" in route.venue.lower()

    def test_already_out_never_gets_a_filing_route(self):
        routes = build_recourse_routes(
            _route_in(
                tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
                agency=UNLICENSED_AGENCY,
            )
        )
        venues = [r.venue for r in routes]
        assert not any("Single Entry Approach" in v for v in venues)
        assert not any("anti-illegal-recruitment" in v for v in venues)
        assert not any("AKSYON" in v for v in venues)

    def test_departed_country_is_not_the_repatriation_bucket(self):
        # Already home: the license fork runs instead of repatriation.
        routes = build_recourse_routes(
            _route_in(tenure=TenureBucket.DEPARTED_COUNTRY, agency=LICENSED_AGENCY)
        )
        venues = [r.venue for r in routes]
        assert any("Single Entry Approach" in v for v in venues)


class TestRegionalOfficeFork:
    """Acceptance: family outside Metro Manila gets the regional route,
    never Manila-centric by default."""

    def test_family_outside_metro_manila_gets_regional_office(self):
        routes = build_recourse_routes(
            _route_in(family_region=FamilyRegion.OUTSIDE_METRO_MANILA)
        )
        assert any(
            "regional/satellite office nearest your family" in r.venue
            for r in routes
        )
        assert not any("NCR" in r.venue for r in routes)

    def test_family_in_metro_manila_gets_ncr_office(self):
        routes = build_recourse_routes(
            _route_in(family_region=FamilyRegion.METRO_MANILA)
        )
        assert any("NCR" in r.venue for r in routes)

    def test_family_region_unset_never_assumes_manila(self):
        routes = build_recourse_routes(_route_in(family_region=None))
        venues = [r.venue for r in routes]
        assert not any("NCR" in v for v in venues)
        assert not any(
            "regional/satellite office nearest your family" in v for v in venues
        )
        assert any("serving your family's location" in v for v in venues)


class TestAksyonFundTier:
    def test_physical_abuse_gets_severe_injury_tier(self):
        assert (
            _aksyon_tier((Grievance.PHYSICAL_ABUSE_OR_DANGER,))
            is AksyonFundTier.SEVERE_INJURY
        )

    def test_unpaid_wages_gets_base_tier(self):
        assert _aksyon_tier((Grievance.UNPAID_WAGES,)) is AksyonFundTier.BASE

    def test_aksyon_route_rides_alongside_licensed_fork(self):
        routes = build_recourse_routes(
            _route_in(
                agency=LICENSED_AGENCY, grievances=(Grievance.UNPAID_WAGES,)
            )
        )
        assert any("AKSYON" in r.venue and "50,000" in r.venue for r in routes)

    def test_aksyon_route_rides_alongside_illegal_recruitment_fork(self):
        routes = build_recourse_routes(
            _route_in(
                agency=UNLICENSED_AGENCY,
                grievances=(Grievance.PHYSICAL_ABUSE_OR_DANGER,),
            )
        )
        assert any("AKSYON" in r.venue and "75,000" in r.venue for r in routes)

    def test_no_grievances_means_no_aksyon_route(self):
        routes = build_recourse_routes(_route_in(grievances=()))
        assert not any("AKSYON" in r.venue for r in routes)


class TestDemoableDoorListsDiffer:
    """Acceptance: same grievance, two agency-license states, visibly
    different door lists."""

    def test_same_grievance_two_license_states_different_doors(self):
        licensed_routes = build_recourse_routes(_route_in(agency=LICENSED_AGENCY))
        unlicensed_routes = build_recourse_routes(_route_in(agency=UNLICENSED_AGENCY))
        licensed_venues = {r.venue for r in licensed_routes}
        unlicensed_venues = {r.venue for r in unlicensed_routes}
        # The door lists are visibly different overall...
        assert licensed_venues != unlicensed_venues
        # ...and specifically: the primary legal venue never appears in
        # both — only the additive AKSYON Fund route (same tier, same
        # grievance either way) is shared between them.
        assert not any("Single Entry Approach" in v for v in unlicensed_venues)
        assert not any("anti-illegal-recruitment" in v for v in licensed_venues)
        shared = licensed_venues & unlicensed_venues
        assert all("AKSYON" in v for v in shared)
