"""``fill_sena_rfa`` (issue #46, PRD #34): the SEnA Request for Assistance,
filled from typed Case + Plan facts — never a blank form handed to her at
1am.

Field list verified against the current published DOLE SEnA RFA form
(SEnA-2024-01 Request for Single Entry Assistance Application, and the
predecessor DOLE-SEnA Form No. 1 still mirrored by several regional DOLE
sites): requesting-party identity, responding-party identity and
address, the nature of the request (checkbox categories), relief sought,
and supporting documents. ``form_title`` and ``filing_note`` are fixed
Literals on :class:`~app.complaint.schema.SenaRfaFields` — this module
can only ever populate them with that exact text.

SEnA's own scope bounds ``nature_of_request`` structurally: only
grievances SEnA can actually hear (money claims, illegal dismissal) may
populate it. A grievance SEnA cannot hear (physical danger, passport
withholding, an exit block) is silently excluded here — it never reaches
the RFA at all, and ``safety_review``'s VENUE_SCOPE_MISMATCH check
guards the free-text narrative against claiming otherwise.
"""

from __future__ import annotations

from app.complaint.schema import (
    AgencyInfo,
    EmployerInfo,
    NatureOfRequest,
    RespondingParty,
    RespondingPartyRole,
    ReliefSought,
    SenaRfaFields,
    WorkerInfo,
)
from app.rules.schema import Citation, Grievance, SourceTier

CIT_SENA_RFA = Citation(
    source_name=(
        "DOLE Single-Entry Approach (SEnA) — Republic Act No. 10396 and "
        "Department Order No. 107-10; SEnA-2024-01 Request for Single "
        "Entry Assistance (SEnA) Application (rev. Nov 2024), the current "
        "Request for Assistance (RFA) form"
    ),
    reference=(
        "RFA field list: requesting-party identity and contact details, "
        "responding-party identity/business address/contact, nature of "
        "complaint (money claims, illegal dismissal, unfair labor "
        "practice, OSH non-compliance), relief sought, and supporting "
        "documents; filable at any DOLE Single-Entry Assistance Desk "
        "Officer (SEADO) or via the DOLE ARMS online portal"
    ),
    url="https://sena.dole.gov.ph/",
    tier=SourceTier.TIER_1,
)

#: SEnA's own scope: only grievances a labor conciliation-mediation venue
#: can actually hear map to a nature_of_request entry. Grievances absent
#: from this table (danger, passport withholding, exit blocking) never
#: populate the RFA — they belong to the MWO/ATN or a criminal track.
_GRIEVANCE_TO_NATURE: dict[Grievance, NatureOfRequest] = {
    Grievance.UNPAID_WAGES: NatureOfRequest.MONEY_CLAIMS,
    Grievance.STATUS_RETALIATION: NatureOfRequest.ILLEGAL_DISMISSAL,
}


class NoSenaClaimError(Exception):
    """Raised when none of the requested grievances is one SEnA can
    hear — the caller must route elsewhere, never file a claims-empty
    RFA."""


def _supporting_documents(*, has_agency: bool, has_wage_loss: bool) -> tuple[str, ...]:
    docs = ["Valid Philippine ID or passport copy"]
    if has_agency:
        docs.append("Overseas Employment Certificate (OEC) or agency contract")
    if has_wage_loss:
        docs.append(
            "Proof of salary (remittance receipts, bank statement, or "
            "payslip)"
        )
    return tuple(docs)


def fill_sena_rfa(
    *,
    worker: WorkerInfo,
    employer: EmployerInfo,
    agency: AgencyInfo,
    grievances: tuple[Grievance, ...],
    has_wage_loss: bool = False,
) -> SenaRfaFields:
    """Deterministically fills the RFA from Case-derived facts.

    Raises :class:`NoSenaClaimError` when no requested grievance is one
    SEnA can hear — the caller (the agent tool wrapper) must surface
    this as a refusal, never as an empty form. This function does not
    check the agency's license status itself: the caller must have
    already cleared ``check_agency_license`` to LICENSED before calling
    this (defense in depth against a future caller wiring this up
    ahead of the gate).
    """
    natures = tuple(
        dict.fromkeys(  # de-duplicated, first-seen order
            _GRIEVANCE_TO_NATURE[g]
            for g in grievances
            if g in _GRIEVANCE_TO_NATURE
        )
    )
    if not natures:
        raise NoSenaClaimError(
            "no requested grievance is one SEnA can hear "
            f"(grievances={[g.value for g in grievances]!r})"
        )

    responding_parties = [
        RespondingParty(
            name=employer.name,
            role=RespondingPartyRole.EMPLOYER,
            address=employer.address,
        )
    ]
    if agency.name:
        responding_parties.append(
            RespondingParty(
                name=agency.name,
                role=RespondingPartyRole.RECRUITMENT_AGENCY,
                address=None,
            )
        )

    return SenaRfaFields(
        requesting_party_name=worker.full_name,
        requesting_party_sex=worker.sex,
        requesting_party_address=worker.ph_address,
        requesting_party_contact=worker.contact,
        responding_parties=tuple(responding_parties),
        nature_of_request=natures,
        relief_sought=(ReliefSought.PAYMENT_OF_CLAIMS,),
        supporting_documents=_supporting_documents(
            has_agency=bool(agency.name), has_wage_loss=has_wage_loss
        ),
        source=CIT_SENA_RFA,
    )
