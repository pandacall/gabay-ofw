"""``safety_review`` fixture suite (issue #46): CI-gating, pure, no
model, no I/O — the fixed leak-check list PRD #34 names: absconding
admissions, claims the venue cannot hear, naming her before she is out,
and the agency-as-respondent leak (departure intent / shelter / location
/ MWO contact).
"""

from __future__ import annotations

from app.complaint.redteam import safety_review
from app.complaint.schema import RedTeamCheckId
from app.rules.schema import Grievance, TenureBucket

SAFE_NARRATIVE = (
    "Maria Santos worked as a domestic worker for the Al Rashid household "
    "in Riyadh from 2024-01-01 to 2026-06-01. She was not paid for the "
    "last three months of her contract. She is requesting payment of her "
    "unpaid wages through the DOLE Single-Entry Approach."
)


class TestCleanNarrativeClears:
    def test_a_purely_factual_narrative_clears(self):
        result = safety_review(
            SAFE_NARRATIVE,
            tenure=TenureBucket.DEPARTED_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is True
        assert result.findings == ()


class TestAbscondingAdmissionIsCaught:
    def test_ran_away_admission_fires(self):
        narrative = SAFE_NARRATIVE + " She ran away from her employer last week."
        result = safety_review(
            narrative,
            tenure=TenureBucket.DEPARTED_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.ABSCONDING_ADMISSION
            for f in result.findings
        )

    def test_tagalog_admission_fires(self):
        narrative = SAFE_NARRATIVE + " Tumakas ako sa amo ko noong isang linggo."
        result = safety_review(
            narrative,
            tenure=TenureBucket.DEPARTED_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.ABSCONDING_ADMISSION
            for f in result.findings
        )


class TestVenueScopeMismatchIsCaught:
    def test_criminal_charges_language_fires(self):
        narrative = SAFE_NARRATIVE + " She wants SEnA to file criminal charges."
        result = safety_review(
            narrative,
            tenure=TenureBucket.DEPARTED_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.VENUE_SCOPE_MISMATCH
            for f in result.findings
        )


class TestAgencyLeakChecksAreCaught:
    def test_departure_intent_leak_fires(self):
        narrative = SAFE_NARRATIVE + " She is planning to leave next week."
        result = safety_review(
            narrative,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.AGENCY_LEAK_DEPARTURE_INTENT
            for f in result.findings
        )

    def test_shelter_leak_fires(self):
        narrative = SAFE_NARRATIVE + " She is currently staying in a shelter."
        result = safety_review(
            narrative,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.AGENCY_LEAK_SHELTER
            for f in result.findings
        )

    def test_location_leak_fires(self):
        narrative = SAFE_NARRATIVE + " Her current address is 12 Olaya Street."
        result = safety_review(
            narrative,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.AGENCY_LEAK_LOCATION
            for f in result.findings
        )

    def test_mwo_contact_leak_fires(self):
        narrative = SAFE_NARRATIVE + " She already spoke to the MWO about this."
        result = safety_review(
            narrative,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.AGENCY_LEAK_MWO_CONTACT
            for f in result.findings
        )


class TestPrematureIdentificationIsStructural:
    """"Naming her before she is out": fires on the facts themselves,
    never clearable by rewording the narrative."""

    def test_acute_grievance_and_not_departed_fires_even_on_a_clean_narrative(
        self,
    ):
        result = safety_review(
            SAFE_NARRATIVE,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.PHYSICAL_ABUSE_OR_DANGER,),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.PREMATURE_IDENTIFICATION
            for f in result.findings
        )

    def test_safety_flag_and_not_departed_fires(self):
        result = safety_review(
            SAFE_NARRATIVE,
            tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
            safety_flags=("PHYSICAL_ASSAULT_ONGOING",),
        )
        assert result.cleared is False
        assert any(
            f.check_id is RedTeamCheckId.PREMATURE_IDENTIFICATION
            for f in result.findings
        )

    def test_acute_grievance_but_already_departed_clears(self):
        result = safety_review(
            SAFE_NARRATIVE,
            tenure=TenureBucket.DEPARTED_COUNTRY,
            grievances=(Grievance.PHYSICAL_ABUSE_OR_DANGER,),
        )
        assert result.cleared is True

    def test_no_acute_grievance_and_not_departed_clears(self):
        result = safety_review(
            SAFE_NARRATIVE,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert result.cleared is True


class TestRevisionClearsOnRewrite:
    def test_a_revised_narrative_without_the_leak_clears(self):
        leaking = SAFE_NARRATIVE + " She is currently staying in a shelter."
        first = safety_review(
            leaking,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert first.cleared is False

        revised = safety_review(
            SAFE_NARRATIVE,
            tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert revised.cleared is True
