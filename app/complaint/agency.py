"""``check_agency_license`` (issue #46, PRD #34): the correctness gate
COMPLAINT_DRAFTER must clear before it fills anything.

An unlicensed agency or a direct hire means SEnA is the wrong instrument:
deployment through an unlicensed agency, or a direct hire for household
work abroad, is illegal recruitment — a criminal-track matter for the
NBI/DMW anti-illegal-recruitment desk, not a DOLE labor money claim. This
module's job is to fork that decision *before* any form is drafted, never
after.

Deterministic lookup, not a live call: the public DMW licensed-agency
list and its query surface is an open research task (PRD #34's Further
Notes lists it explicitly). This ships a small, hand-built fixture set
pending that integration — entries are illustrative fixtures for
exercising the LICENSED / DELISTED / CANCELLED / EXPIRED / NOT_FOUND
branches, not a claim about any real company's current standing. Wiring
a real DMW query behind ``check_agency_license``'s same signature is a
drop-in replacement; nothing above this function needs to change.

Fail closed (same posture as UNKNOWN-country routing elsewhere in this
codebase): only a positive LICENSED match clears SEnA to proceed. A name
that does not match anything in the fixture is NOT_FOUND, not "assumed
licensed" — but it is also not asserted illegal, since we have not
confirmed it is actually unlicensed. The caller (COMPLAINT_DRAFTER's tool
wrapper) turns DELISTED/CANCELLED/EXPIRED/DIRECT_HIRE into the definitive
illegal-recruitment refusal, and NOT_FOUND into a distinct
"go verify at dmw.gov.ph first" refusal that does not accuse anyone.
"""

from __future__ import annotations

import unicodedata
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.complaint.schema import AgencyLicenseResult, AgencyLicenseStatus
from app.rules.schema import Citation, SourceTier

CIT_DMW_AGENCY_LIST = Citation(
    source_name="DMW Licensed Recruitment Agencies directory",
    reference=(
        "Public searchable list of land-based recruitment/manning "
        "agencies licensed by the Department of Migrant Workers, by "
        "agency name or license number; license status shown as Valid, "
        "Delisted, Cancelled, Suspended, or Expired"
    ),
    url="https://www.dmw.gov.ph/licensed-recruitment-agencies",
    tier=SourceTier.TIER_1,
)


def _normalize(name: str) -> str:
    """Lowercase, diacritics stripped, punctuation to spaces, collapsed —
    same normalization discipline as DEBUNKER's claim classifier, so
    "Sample Overseas Manpower Services, Inc." and "sample overseas
    manpower services inc" resolve to the same fixture row."""
    decomposed = unicodedata.normalize("NFD", name.strip().lower())
    stripped = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    cleaned = "".join(ch if ch.isalnum() else " " for ch in stripped)
    return " ".join(cleaned.split())


class AgencyRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    normalized_name: str
    display_name: str
    license_no: Optional[str] = None
    status: AgencyLicenseStatus


def _record(display_name: str, license_no: str, status: AgencyLicenseStatus) -> AgencyRecord:
    return AgencyRecord(
        normalized_name=_normalize(display_name),
        display_name=display_name,
        license_no=license_no,
        status=status,
    )


#: Illustrative fixture pending the live DMW query surface (see module
#: docstring). Exercises every branch ``check_agency_license`` forks on.
AGENCY_DIRECTORY: tuple[AgencyRecord, ...] = (
    _record(
        "Sample Overseas Manpower Services, Inc.",
        "POEA-L-000001-FIXTURE",
        AgencyLicenseStatus.LICENSED,
    ),
    _record(
        "Placeholder Global Recruitment Corp.",
        "POEA-L-000002-FIXTURE",
        AgencyLicenseStatus.DELISTED,
    ),
    _record(
        "Fixture Staffing Solutions Co.",
        "POEA-L-000003-FIXTURE",
        AgencyLicenseStatus.CANCELLED,
    ),
    _record(
        "Testcase Manning Agency, Inc.",
        "POEA-L-000004-FIXTURE",
        AgencyLicenseStatus.EXPIRED,
    ),
)

_BY_NORMALIZED_NAME: dict[str, AgencyRecord] = {
    record.normalized_name: record for record in AGENCY_DIRECTORY
}


def check_agency_license(
    name: Optional[str], *, direct_hire: bool = False
) -> AgencyLicenseResult:
    """Looks up ``name`` against the (fixture) DMW licensed-agency list.

    ``direct_hire`` short-circuits to DIRECT_HIRE regardless of ``name``
    — hiring directly for household work abroad, without a licensed
    agency, is itself the wrong-venue signal. A blank/omitted name with
    ``direct_hire=False`` is NOT_FOUND: never guessed licensed.
    """
    if direct_hire:
        return AgencyLicenseResult(
            status=AgencyLicenseStatus.DIRECT_HIRE,
            source=CIT_DMW_AGENCY_LIST,
        )
    if not name or not name.strip():
        return AgencyLicenseResult(
            status=AgencyLicenseStatus.NOT_FOUND,
            source=CIT_DMW_AGENCY_LIST,
        )
    record = _BY_NORMALIZED_NAME.get(_normalize(name))
    if record is None:
        return AgencyLicenseResult(
            status=AgencyLicenseStatus.NOT_FOUND,
            source=CIT_DMW_AGENCY_LIST,
        )
    return AgencyLicenseResult(
        status=record.status,
        matched_name=record.display_name,
        license_no=record.license_no,
        source=CIT_DMW_AGENCY_LIST,
    )


def is_wrong_venue(result: AgencyLicenseResult) -> bool:
    """Whether this status means SEnA is the wrong instrument.

    Only a confirmed LICENSED match clears SEnA (fail closed) — every
    other status, including an unmatched name, forks away from SEnA.
    """
    return result.status is not AgencyLicenseStatus.LICENSED
