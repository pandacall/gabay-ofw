"""``fill_sena_rfa`` tests (issue #46): form-fill from a Case + Plan-shaped
fixture. Pure, no model — verifies the venue-scope filter (SEnA cannot
hear danger/passport/exit grievances) and responding-party assembly.
"""

from __future__ import annotations

import pytest

from app.complaint.schema import (
    AgencyInfo,
    EmployerInfo,
    NatureOfRequest,
    RespondingPartyRole,
    WorkerInfo,
)
from app.complaint.sena_form import NoSenaClaimError, fill_sena_rfa
from app.rules.schema import Grievance

WORKER = WorkerInfo(full_name="Maria Santos", sex="female", ph_address="Manila")
EMPLOYER = EmployerInfo(name="Al Rashid Household", address="Riyadh")


class TestNatureOfRequestMapping:
    def test_unpaid_wages_maps_to_money_claims(self):
        fields = fill_sena_rfa(
            worker=WORKER,
            employer=EMPLOYER,
            agency=AgencyInfo(name="Sample Overseas Manpower Services, Inc."),
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert fields.nature_of_request == (NatureOfRequest.MONEY_CLAIMS,)

    def test_status_retaliation_maps_to_illegal_dismissal(self):
        fields = fill_sena_rfa(
            worker=WORKER,
            employer=EMPLOYER,
            agency=AgencyInfo(direct_hire=False),
            grievances=(Grievance.STATUS_RETALIATION,),
        )
        assert fields.nature_of_request == (NatureOfRequest.ILLEGAL_DISMISSAL,)

    def test_grievances_sena_cannot_hear_are_excluded(self):
        fields = fill_sena_rfa(
            worker=WORKER,
            employer=EMPLOYER,
            agency=AgencyInfo(),
            grievances=(Grievance.UNPAID_WAGES, Grievance.PHYSICAL_ABUSE_OR_DANGER),
        )
        # Only the money-claims nature is set; danger never populates a
        # SEnA RFA — SEnA cannot hear it.
        assert fields.nature_of_request == (NatureOfRequest.MONEY_CLAIMS,)

    def test_no_sena_coverable_grievance_raises(self):
        with pytest.raises(NoSenaClaimError):
            fill_sena_rfa(
                worker=WORKER,
                employer=EMPLOYER,
                agency=AgencyInfo(),
                grievances=(Grievance.PASSPORT_WITHHELD,),
            )


class TestRespondingParties:
    def test_employer_always_present(self):
        fields = fill_sena_rfa(
            worker=WORKER,
            employer=EMPLOYER,
            agency=AgencyInfo(),
            grievances=(Grievance.UNPAID_WAGES,),
        )
        roles = {p.role for p in fields.responding_parties}
        assert RespondingPartyRole.EMPLOYER in roles
        assert RespondingPartyRole.RECRUITMENT_AGENCY not in roles

    def test_agency_added_as_second_respondent_when_named(self):
        fields = fill_sena_rfa(
            worker=WORKER,
            employer=EMPLOYER,
            agency=AgencyInfo(name="Sample Overseas Manpower Services, Inc."),
            grievances=(Grievance.UNPAID_WAGES,),
        )
        roles = {p.role for p in fields.responding_parties}
        assert roles == {
            RespondingPartyRole.EMPLOYER,
            RespondingPartyRole.RECRUITMENT_AGENCY,
        }


class TestRequestingPartyAndSource:
    def test_requesting_party_from_worker_info(self):
        fields = fill_sena_rfa(
            worker=WORKER,
            employer=EMPLOYER,
            agency=AgencyInfo(),
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert fields.requesting_party_name == "Maria Santos"
        assert fields.requesting_party_sex.value == "female"

    def test_source_citation_is_present(self):
        fields = fill_sena_rfa(
            worker=WORKER,
            employer=EMPLOYER,
            agency=AgencyInfo(),
            grievances=(Grievance.UNPAID_WAGES,),
        )
        assert fields.source.source_name
        assert fields.source.url.startswith("http")

    def test_supporting_documents_include_wage_proof_when_wage_loss_given(self):
        fields = fill_sena_rfa(
            worker=WORKER,
            employer=EMPLOYER,
            agency=AgencyInfo(),
            grievances=(Grievance.UNPAID_WAGES,),
            has_wage_loss=True,
        )
        assert any("salary" in doc.lower() for doc in fields.supporting_documents)
