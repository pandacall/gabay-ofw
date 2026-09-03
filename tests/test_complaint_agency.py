"""``check_agency_license`` fixture suite (issue #46): CI-gating, pure,
no model, no I/O — exercises every branch the correctness gate forks on.
"""

from __future__ import annotations

from app.complaint.agency import (
    AGENCY_DIRECTORY,
    check_agency_license,
    is_wrong_venue,
)
from app.complaint.schema import AgencyLicenseStatus


class TestLicensedAgencyClears:
    def test_exact_name_match_is_licensed(self):
        result = check_agency_license("Sample Overseas Manpower Services, Inc.")
        assert result.status is AgencyLicenseStatus.LICENSED
        assert not is_wrong_venue(result)
        assert result.license_no

    def test_case_and_punctuation_insensitive_match(self):
        result = check_agency_license(
            "sample overseas manpower services inc"
        )
        assert result.status is AgencyLicenseStatus.LICENSED
        assert result.matched_name == "Sample Overseas Manpower Services, Inc."

    def test_whitespace_padded_name_still_matches(self):
        result = check_agency_license(
            "   Sample Overseas Manpower Services, Inc.   "
        )
        assert result.status is AgencyLicenseStatus.LICENSED


class TestUnlicensedStatusesForkAwayFromSena:
    def test_delisted_agency_is_wrong_venue(self):
        result = check_agency_license("Placeholder Global Recruitment Corp.")
        assert result.status is AgencyLicenseStatus.DELISTED
        assert is_wrong_venue(result)

    def test_cancelled_agency_is_wrong_venue(self):
        result = check_agency_license("Fixture Staffing Solutions Co.")
        assert result.status is AgencyLicenseStatus.CANCELLED
        assert is_wrong_venue(result)

    def test_expired_agency_is_wrong_venue(self):
        result = check_agency_license("Testcase Manning Agency, Inc.")
        assert result.status is AgencyLicenseStatus.EXPIRED
        assert is_wrong_venue(result)


class TestDirectHireForksRegardlessOfName:
    def test_direct_hire_true_overrides_any_name(self):
        result = check_agency_license(
            "Sample Overseas Manpower Services, Inc.", direct_hire=True
        )
        assert result.status is AgencyLicenseStatus.DIRECT_HIRE
        assert is_wrong_venue(result)

    def test_direct_hire_with_no_name(self):
        result = check_agency_license(None, direct_hire=True)
        assert result.status is AgencyLicenseStatus.DIRECT_HIRE


class TestUnknownNameFailsClosedToNotFound:
    def test_unmatched_name_is_not_found_not_licensed(self):
        result = check_agency_license("Totally Made Up Agency Name Ltd.")
        assert result.status is AgencyLicenseStatus.NOT_FOUND
        assert is_wrong_venue(result)

    def test_blank_name_is_not_found(self):
        result = check_agency_license("   ")
        assert result.status is AgencyLicenseStatus.NOT_FOUND

    def test_none_name_is_not_found(self):
        result = check_agency_license(None)
        assert result.status is AgencyLicenseStatus.NOT_FOUND


class TestFixtureIntegrity:
    def test_every_fixture_row_has_a_tier1_source(self):
        for record in AGENCY_DIRECTORY:
            assert record.status in AgencyLicenseStatus

    def test_only_licensed_status_clears(self):
        for status in AgencyLicenseStatus:
            from app.complaint.schema import AgencyLicenseResult
            from app.complaint.agency import CIT_DMW_AGENCY_LIST

            result = AgencyLicenseResult(status=status, source=CIT_DMW_AGENCY_LIST)
            expected_wrong = status is not AgencyLicenseStatus.LICENSED
            assert is_wrong_venue(result) is expected_wrong
