"""Per-venue intake checklists (issue #45): reviewable data, source per row.

Each row records what one venue's PUBLISHED intake asks for, whether it
is required or merely strengthens the request, the published source it
was taken from, and the source's ADR-0005 tier. Tribunal persuasion is
explicitly out of scope: a row says what the office will ask her for,
never what will win a case — evidentiary weight is not published and
sourcing it would mean inventing it (PRD #34, Out of Scope).

Substitutes encode the acquisition reality the checklist set-difference
can't: an OFW domestic worker rarely holds her contract, and Gulf
household employers issue no payslips — remittance receipts and bank
statements are the obtainable proxies for the same facts.

Every step a checklist implies (photograph a document, request a copy)
is protective and reversible, so ADR-0005's irreversibility bound is
never in play; the tier is recorded per row regardless.
"""

from __future__ import annotations

from app.proof.schema import (
    ArtifactType,
    ChecklistRow,
    RequirementLevel,
    Venue,
)
from app.rules.schema import Citation, SourceTier

_CIT_SENA = Citation(
    source_name=(
        "DOLE Single-Entry Approach (SEnA) — Republic Act No. 10396 and "
        "Department Order No. 107-10, Request for Assistance (RFA) form"
    ),
    reference=(
        "The RFA form's field list and filing requirements: identity of "
        "the requesting party, respondent's name and address, and the "
        "nature of the request; supporting documents are received at "
        "conciliation-mediation"
    ),
    url="https://sena.dole.gov.ph/",
    tier=SourceTier.TIER_1,
)

_CIT_OWWA = Citation(
    source_name=(
        "OWWA Omnibus Policies (Board of Trustees Resolution No. 038, "
        "s. 2016) — membership and proof-of-employment requirements"
    ),
    reference=(
        "Voluntary membership and welfare-program intake require proof "
        "of active employment abroad: employment contract, and in its "
        "absence a work permit / residence ID, company ID, payslip, or "
        "proof of monthly income"
    ),
    url="https://owwa.gov.ph/",
    tier=SourceTier.TIER_1,
)

_CIT_MWO_ATN = Citation(
    source_name=(
        "DMW — Migrant Workers Office (MWO) Assistance-to-Nationals "
        "case intake"
    ),
    reference=(
        "MWO welfare-case intake asks for the worker's identity and "
        "employment papers (passport, contract, residence ID) plus "
        "whatever evidence of the grievance the worker can safely "
        "provide"
    ),
    url="https://dmw.gov.ph/",
    tier=SourceTier.TIER_1,
)


INTAKE_CHECKLISTS: tuple[ChecklistRow, ...] = (
    # ------------------------------------------------------------------
    # SEnA Request for Assistance (RFA field list)
    # ------------------------------------------------------------------
    ChecklistRow(
        row_id="sena-valid-id",
        venue=Venue.SENA_RFA,
        artifact=ArtifactType.VALID_PH_ID,
        requirement=RequirementLevel.REQUIRED,
        substitutes=(ArtifactType.PASSPORT_COPY,),
        purpose=(
            "Identifies the requesting party on the RFA form; any valid "
            "government ID or the passport serves"
        ),
        source=_CIT_SENA,
        tier=SourceTier.TIER_1,
    ),
    ChecklistRow(
        row_id="sena-employment-contract",
        venue=Venue.SENA_RFA,
        artifact=ArtifactType.EMPLOYMENT_CONTRACT,
        requirement=RequirementLevel.STRENGTHENS,
        substitutes=(
            ArtifactType.OEC,
            ArtifactType.AGENCY_RECEIPT_OR_CONTRACT,
            ArtifactType.COMPANY_ID,
        ),
        purpose=(
            "Shows the employment relationship and the agreed salary the "
            "money claim is measured against"
        ),
        source=_CIT_SENA,
        tier=SourceTier.TIER_1,
    ),
    ChecklistRow(
        row_id="sena-oec",
        venue=Venue.SENA_RFA,
        artifact=ArtifactType.OEC,
        requirement=RequirementLevel.STRENGTHENS,
        substitutes=(ArtifactType.AGENCY_RECEIPT_OR_CONTRACT,),
        purpose=(
            "Shows deployment through a licensed agency — the hook for "
            "naming the agency as respondent"
        ),
        source=_CIT_SENA,
        tier=SourceTier.TIER_1,
    ),
    ChecklistRow(
        row_id="sena-wage-evidence",
        venue=Venue.SENA_RFA,
        artifact=ArtifactType.PAYSLIP,
        requirement=RequirementLevel.STRENGTHENS,
        substitutes=(
            ArtifactType.REMITTANCE_RECEIPT,
            ArtifactType.BANK_STATEMENT,
            ArtifactType.CHAT_SCREENSHOT,
        ),
        purpose=(
            "Shows what was actually paid, so the unpaid difference can "
            "be computed at conciliation"
        ),
        source=_CIT_SENA,
        tier=SourceTier.TIER_1,
    ),
    # ------------------------------------------------------------------
    # OWWA proof-of-employment package
    # ------------------------------------------------------------------
    ChecklistRow(
        row_id="owwa-passport",
        venue=Venue.OWWA_PROOF_OF_EMPLOYMENT,
        artifact=ArtifactType.PASSPORT_COPY,
        requirement=RequirementLevel.REQUIRED,
        substitutes=(),
        purpose="Identifies the member; the bio page is what is checked",
        source=_CIT_OWWA,
        tier=SourceTier.TIER_1,
    ),
    ChecklistRow(
        row_id="owwa-proof-of-employment",
        venue=Venue.OWWA_PROOF_OF_EMPLOYMENT,
        artifact=ArtifactType.EMPLOYMENT_CONTRACT,
        requirement=RequirementLevel.REQUIRED,
        substitutes=(
            ArtifactType.RESIDENCE_ID_COPY,
            ArtifactType.COMPANY_ID,
            ArtifactType.PAYSLIP,
            ArtifactType.REMITTANCE_RECEIPT,
        ),
        purpose=(
            "Proves active employment abroad; OWWA's own list accepts a "
            "work permit / residence ID, company ID, or proof of income "
            "when there is no contract"
        ),
        source=_CIT_OWWA,
        tier=SourceTier.TIER_1,
    ),
    ChecklistRow(
        row_id="owwa-membership-record",
        venue=Venue.OWWA_PROOF_OF_EMPLOYMENT,
        artifact=ArtifactType.OWWA_MEMBERSHIP_PROOF,
        requirement=RequirementLevel.STRENGTHENS,
        substitutes=(ArtifactType.OEC,),
        purpose=(
            "Speeds verification of an existing membership; OWWA can also "
            "look it up from the passport"
        ),
        source=_CIT_OWWA,
        tier=SourceTier.TIER_1,
    ),
    # ------------------------------------------------------------------
    # MWO / Assistance-to-Nationals case intake
    # ------------------------------------------------------------------
    ChecklistRow(
        row_id="mwo-passport",
        venue=Venue.MWO_ATN_INTAKE,
        artifact=ArtifactType.PASSPORT_COPY,
        requirement=RequirementLevel.REQUIRED,
        substitutes=(ArtifactType.RESIDENCE_ID_COPY,),
        purpose=(
            "Identifies the worker and her status; a residence ID (iqama "
            "/ QID) serves when the employer holds the passport"
        ),
        source=_CIT_MWO_ATN,
        tier=SourceTier.TIER_1,
    ),
    ChecklistRow(
        row_id="mwo-employment-contract",
        venue=Venue.MWO_ATN_INTAKE,
        artifact=ArtifactType.EMPLOYMENT_CONTRACT,
        requirement=RequirementLevel.STRENGTHENS,
        substitutes=(
            ArtifactType.OEC,
            ArtifactType.AGENCY_RECEIPT_OR_CONTRACT,
            ArtifactType.RESIDENCE_ID_COPY,
        ),
        purpose=(
            "Names the employer and the agreed terms the MWO raises with "
            "the employer or agency"
        ),
        source=_CIT_MWO_ATN,
        tier=SourceTier.TIER_1,
    ),
    ChecklistRow(
        row_id="mwo-wage-evidence",
        venue=Venue.MWO_ATN_INTAKE,
        artifact=ArtifactType.PAYSLIP,
        requirement=RequirementLevel.STRENGTHENS,
        substitutes=(
            ArtifactType.REMITTANCE_RECEIPT,
            ArtifactType.BANK_STATEMENT,
            ArtifactType.CHAT_SCREENSHOT,
        ),
        purpose=(
            "Shows the payment history behind a wage complaint; Gulf "
            "household employers rarely issue payslips, so remittance "
            "receipts are the usual proxy"
        ),
        source=_CIT_MWO_ATN,
        tier=SourceTier.TIER_1,
    ),
    ChecklistRow(
        row_id="mwo-grievance-evidence",
        venue=Venue.MWO_ATN_INTAKE,
        artifact=ArtifactType.CHAT_SCREENSHOT,
        requirement=RequirementLevel.STRENGTHENS,
        substitutes=(
            ArtifactType.PHOTO_OF_INJURY,
            ArtifactType.MEDICAL_RECORD,
            ArtifactType.PHOTO_OF_WORKPLACE,
        ),
        purpose=(
            "Documents the grievance itself — messages, photos, or "
            "medical records, whatever can be captured safely"
        ),
        source=_CIT_MWO_ATN,
        tier=SourceTier.TIER_1,
    ),
)


def checklist_for(venue: Venue) -> tuple[ChecklistRow, ...]:
    """All rows for one venue, in review order."""
    return tuple(row for row in INTAKE_CHECKLISTS if row.venue is venue)


def required_artifacts(venue: Venue) -> tuple[ArtifactType, ...]:
    """The venue's REQUIRED artifacts."""
    return tuple(
        row.artifact
        for row in checklist_for(venue)
        if row.requirement is RequirementLevel.REQUIRED
    )


def obtainable_substitutes(venue: Venue, artifact: ArtifactType) -> tuple[ArtifactType, ...]:
    """Substitutes for one artifact at one venue, best first."""
    for row in checklist_for(venue):
        if row.artifact is artifact:
            return row.substitutes
    return ()
