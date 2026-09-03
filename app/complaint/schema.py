"""Typed boundary of COMPLAINT_DRAFTER (issue #46, PRD #34).

COMPLAINT_DRAFTER is a single-turn specialist: it sees NONE of the
conversation. Its entire input is :class:`ComplaintDraftIn` — Case-derived
facts (worker, employer, agency, country, tenure, grievances, wage loss)
plus the verified :class:`~app.sequencer.Plan` FILING_SEQUENCER already
built this turn — and its entire output is :class:`ComplaintDraftOut`.
There is deliberately no free-text ``request`` parameter anywhere.

Everything the safety story depends on is structural:

* **Fills, never submits.** No field anywhere under this module names an
  endpoint, a submission id, or a "submitted" status; :class:`FormDraft`
  carries a rendered PDF and structured field values, nothing else. There
  is no function in :mod:`app.complaint` that performs network I/O.
* **The Arabic deliverable is arithmetic-only.** :class:`ArabicLossCalculation`
  cannot hold a free-text field: every value is a closed
  :class:`ArabicLossLineLabel` enum, a pattern-constrained decimal amount,
  a pattern-constrained ISO date, or a :class:`~app.proof.schema.Currency`
  enum. An argumentative Arabic draft is unrepresentable, not merely
  discouraged.
* **Only a red-team-cleared draft ships.** :class:`FormDraft` refuses to
  validate unless its own ``red_team`` result is ``cleared`` — a draft
  still carrying an open finding cannot cross into the typed output at
  all.
* **Exactly one of three outcomes.** :class:`ComplaintDraftOut` carries a
  :class:`FormDraft`, an :class:`IllegalRecruitmentRefusal` (wrong
  venue), or a :class:`PrematureFilingRefusal` (right venue, unsafe
  moment) — never more than one and never none. The drafter cannot
  half-refuse.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, computed_field, field_validator, model_validator

from app.case import SAFETY_FLAGS
from app.proof.schema import Currency, DecimalAmount, IsoDate
from app.rules.schema import Citation, Grievance, Jurisdiction, TenureBucket
from app.sequencer import Plan

Language = Literal["en", "tl", "taglish", "ceb", "other"]

# ---------------------------------------------------------------------------
# ComplaintDraftIn — closed-enum input_schema, no free-text request field.
# ---------------------------------------------------------------------------


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"


class WorkerInfo(BaseModel):
    """The requesting party. Her own name/address are not adversarial
    input (unlike OCR'd employer text) so they are plain, required
    strings — never optional-away into a blank RFA."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    full_name: str
    sex: Optional[Sex] = None
    ph_address: Optional[str] = None
    contact: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("full_name is required")
        return value


class EmployerInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    address: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("name is required")
        return value


class AgencyInfo(BaseModel):
    """Either a named recruitment agency, or a direct hire. Never both —
    ``check_agency_license`` treats direct hire as its own wrong-venue
    signal regardless of any name."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: Optional[str] = None
    direct_hire: bool = False

    @model_validator(mode="after")
    def _mutually_exclusive(self) -> "AgencyInfo":
        if self.direct_hire and self.name:
            raise ValueError(
                "direct_hire and an agency name are mutually exclusive"
            )
        return self


class OtherClaimLabel(str, Enum):
    """Closed vocabulary of additive wage-loss line items beyond the
    base monthly-salary x months-unpaid arithmetic."""

    UNPAID_OVERTIME = "unpaid_overtime"
    WITHHELD_FINAL_PAY = "withheld_final_pay"
    UNPAID_BENEFITS = "unpaid_benefits"
    UNRETURNED_PLACEMENT_FEE = "unreturned_placement_fee"


class OtherClaimAmount(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: OtherClaimLabel
    amount: DecimalAmount


class WageLossInput(BaseModel):
    """Everything ``compute_wage_loss`` needs. Every amount and date is
    pattern-constrained (:data:`~app.proof.schema.DecimalAmount` /
    :data:`~app.proof.schema.IsoDate`) — nothing prose-shaped survives."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    monthly_salary: DecimalAmount
    currency: Currency
    months_unpaid: int
    period_start: IsoDate
    period_end: IsoDate
    other_claims: tuple[OtherClaimAmount, ...] = ()

    @field_validator("months_unpaid")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("months_unpaid must be at least 1")
        return value


def _validate_safety_flags(value: tuple[str, ...]) -> tuple[str, ...]:
    unknown = [flag for flag in value if flag not in SAFETY_FLAGS]
    if unknown:
        raise ValueError(f"unknown safety flag(s): {unknown!r}")
    return value


class ComplaintDraftIn(BaseModel):
    """COMPLAINT_DRAFTER's ``input_schema``: Case-derived facts plus Plan.

    Every field DISPATCHER supplies comes from the Case it already holds
    (worker/employer/agency identity, country, tenure, grievances,
    safety flags) or from this turn's own FILING_SEQUENCER output
    (``plan``) — never a bare ``request: string``.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    worker: WorkerInfo
    employer: EmployerInfo
    agency: AgencyInfo
    country: Jurisdiction
    tenure: TenureBucket
    grievances: tuple[Grievance, ...]
    wage_loss: Optional[WageLossInput] = None
    plan: Optional[Plan] = None
    #: Safety flags already on her Case (add-only there; read-only here —
    #: the drafter cannot clear one, it only informs the red-team's
    #: PREMATURE_IDENTIFICATION check).
    safety_flags: tuple[str, ...] = ()
    #: Structural inputs to the agency-as-respondent leak check (issue
    #: #46): true facts the draft must never reveal to a party in
    #: contact with the employer.
    in_shelter: bool = False
    spoke_to_mwo: bool = False
    language: Language = "en"

    @field_validator("grievances")
    @classmethod
    def _non_empty(
        cls, value: tuple[Grievance, ...]
    ) -> tuple[Grievance, ...]:
        if not value:
            raise ValueError("grievances must contain at least one value")
        return value

    @field_validator("safety_flags")
    @classmethod
    def _known_flags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_safety_flags(value)


# ---------------------------------------------------------------------------
# check_agency_license's typed result.
# ---------------------------------------------------------------------------


class AgencyLicenseStatus(str, Enum):
    """Statuses ``check_agency_license`` may return. Only ``LICENSED``
    clears SEnA to proceed (fail closed, ADR-consistent with the rest of
    this codebase's UNKNOWN-is-most-restrictive posture)."""

    LICENSED = "licensed"
    DELISTED = "delisted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"
    DIRECT_HIRE = "direct_hire"


class AgencyLicenseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: AgencyLicenseStatus
    matched_name: Optional[str] = None
    license_no: Optional[str] = None
    source: Citation


# ---------------------------------------------------------------------------
# The illegal-recruitment refusal — first-class, never a half-formed form.
# ---------------------------------------------------------------------------

IllegalRecruitmentReason = Literal[
    "UNLICENSED_AGENCY", "DIRECT_HIRE", "AGENCY_STATUS_UNVERIFIED"
]

#: Fixed, hand-written refusal lines — never composed by the model.
REFUSAL_MESSAGES: dict[IllegalRecruitmentReason, str] = {
    "UNLICENSED_AGENCY": (
        "The agency you named does not show as licensed on the DMW "
        "list. SEnA is the wrong venue for this — deployment through an "
        "unlicensed agency is illegal recruitment, a criminal-track "
        "matter, not a labor money claim. I will not fill a SEnA form "
        "for the wrong office."
    ),
    "DIRECT_HIRE": (
        "You told me there was no licensed agency — a direct hire for "
        "household work abroad. SEnA is the wrong venue for this: it is "
        "an illegal-recruitment matter, a criminal-track case, not a "
        "labor money claim. I will not fill a SEnA form for the wrong "
        "office."
    ),
    "AGENCY_STATUS_UNVERIFIED": (
        "I could not verify that agency on the DMW licensed-agency "
        "list. I won't fill a SEnA form until it is confirmed licensed "
        "— please check the agency's name and license number against "
        "dmw.gov.ph, or the MWO can verify it for you."
    ),
}


class IllegalRecruitmentRefusal(BaseModel):
    """The drafter's first-class refusal: no form, routed instead.

    ``message`` is validated against the fixed :data:`REFUSAL_MESSAGES`
    table for its ``reason`` — the model cannot compose its own wording
    here any more than FILING_SEQUENCER can compose its own
    ``held_refusal`` text.
    """

    model_config = ConfigDict(frozen=True)

    reason: IllegalRecruitmentReason
    agency_status: AgencyLicenseStatus
    message: str
    #: Directory routing rows for the illegal-recruitment / anti-illegal
    #: recruitment track (DMW hotline, MWO), resolved server-side.
    routing: dict

    @model_validator(mode="after")
    def _fixed_message(self) -> "IllegalRecruitmentRefusal":
        if self.message != REFUSAL_MESSAGES[self.reason]:
            raise ValueError(
                f"message for reason {self.reason!r} must be the fixed "
                "REFUSAL_MESSAGES text, verbatim"
            )
        return self


#: The fixed, hand-written line for the premature-identification refusal
#: — never composed by the model, mirroring ``held_refusal_card``'s
#: as-is-text discipline (ADR-0006: an uncited/unsafe filing under a
#: verified-looking UI is worse than none).
PREMATURE_FILING_MESSAGE = (
    "You have an urgent safety grievance and you are still with this "
    "employer. Filing a named complaint now would put your name in front "
    "of a party still in contact with your employer before you are "
    "safely out. Please get to safety and speak with the MWO first — "
    "I will draft this complaint once you are out."
)


class PrematureFilingRefusal(BaseModel):
    """The drafter's second refusal mode: right venue, wrong moment.

    Fires when an acute grievance or safety flag is on her Case and she
    has not yet departed the country (``tenure`` is not
    ``DEPARTED_COUNTRY``) — naming her in a filing a party in contact
    with her employer will read is itself the risk, regardless of what
    the narrative says. Unlike a red-team text finding, no rewording
    clears this: only her situation changing does.
    """

    model_config = ConfigDict(frozen=True)

    message: Literal[
        "You have an urgent safety grievance and you are still with this "
        "employer. Filing a named complaint now would put your name in "
        "front of a party still in contact with your employer before "
        "you are safely out. Please get to safety and speak with the "
        "MWO first — I will draft this complaint once you are out."
    ] = PREMATURE_FILING_MESSAGE
    #: MWO/Safe-Floor routing rows, resolved server-side.
    routing: dict


# ---------------------------------------------------------------------------
# Red-team: the fixed leak-check list (issue #46).
# ---------------------------------------------------------------------------


class RedTeamCheckId(str, Enum):
    """The fixed checklist ``safety_review`` runs. Closed set — a finding
    naming anything else is unrepresentable."""

    ABSCONDING_ADMISSION = "absconding_admission"
    VENUE_SCOPE_MISMATCH = "venue_scope_mismatch"
    PREMATURE_IDENTIFICATION = "premature_identification"
    AGENCY_LEAK_DEPARTURE_INTENT = "agency_leak_departure_intent"
    AGENCY_LEAK_SHELTER = "agency_leak_shelter"
    AGENCY_LEAK_LOCATION = "agency_leak_location"
    AGENCY_LEAK_MWO_CONTACT = "agency_leak_mwo_contact"


class RedTeamFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_id: RedTeamCheckId
    matched_excerpt: Optional[str] = None
    guidance: str


class RedTeamResult(BaseModel):
    """``cleared`` and ``findings`` are never both true and both empty at
    once: a cleared review carries no findings, and an uncleared one
    must name at least one."""

    model_config = ConfigDict(frozen=True)

    cleared: bool
    findings: tuple[RedTeamFinding, ...] = ()
    revision_count: int = 0

    @model_validator(mode="after")
    def _consistent(self) -> "RedTeamResult":
        if self.cleared and self.findings:
            raise ValueError("a cleared review carries no findings")
        if not self.cleared and not self.findings:
            raise ValueError(
                "an uncleared review must name at least one finding"
            )
        return self


# ---------------------------------------------------------------------------
# The Arabic deliverable: arithmetic ONLY, structurally.
# ---------------------------------------------------------------------------


class ArabicLossLineLabel(str, Enum):
    """Closed vocabulary of loss-calculation line items. Each member maps
    to a FIXED Arabic label string in :data:`ARABIC_LABELS` — never
    model-generated."""

    MONTHLY_SALARY = "monthly_salary"
    UNPAID_OVERTIME = "unpaid_overtime"
    WITHHELD_FINAL_PAY = "withheld_final_pay"
    UNPAID_BENEFITS = "unpaid_benefits"
    UNRETURNED_PLACEMENT_FEE = "unreturned_placement_fee"


#: Fixed Arabic labels, hand-written, never generated. The only Arabic
#: TEXT this module ever ships; every other Arabic-adjacent field is a
#: number or an ISO date.
ARABIC_LABELS: dict[ArabicLossLineLabel, str] = {
    ArabicLossLineLabel.MONTHLY_SALARY: "الراتب الشهري",
    ArabicLossLineLabel.UNPAID_OVERTIME: "أجر إضافي غير مدفوع",
    ArabicLossLineLabel.WITHHELD_FINAL_PAY: "مستحقات نهاية الخدمة المحتجزة",
    ArabicLossLineLabel.UNPAID_BENEFITS: "استحقاقات غير مدفوعة",
    ArabicLossLineLabel.UNRETURNED_PLACEMENT_FEE: "رسوم توظيف غير مستردة",
}
ARABIC_TOTAL_LABEL = "المجموع"
ARABIC_PERIOD_LABEL = "الفترة"


class ArabicLossLine(BaseModel):
    """One arithmetic line. ``label`` is a closed enum; ``amount`` is a
    pattern-constrained decimal string — no field on this model can hold
    prose, in any language. ``label_ar`` is a ``computed_field`` so the
    fixed Arabic text is actually present in ``model_dump()`` /
    ``model_dump_json()`` output — the UI (and this line's own JSON
    payload) carries the Arabic label itself, not just a lookup key."""

    model_config = ConfigDict(frozen=True)

    label: ArabicLossLineLabel
    amount: DecimalAmount
    currency: Currency

    @computed_field  # type: ignore[prop-decorator]
    @property
    def label_ar(self) -> str:
        return ARABIC_LABELS[self.label]


class ArabicLossCalculation(BaseModel):
    """The arithmetic-only Arabic deliverable (PRD #46): amounts, dates,
    and a total — nothing argumentative, nothing free-text, in either
    language. ``total_amount`` is independently re-checked against the
    sum of ``lines`` so a drifted total cannot ship. ``total_label_ar``
    and ``period_label_ar`` are fixed Arabic text, computed so they
    serialize with the rest of the payload."""

    model_config = ConfigDict(frozen=True)

    period_start: IsoDate
    period_end: IsoDate
    lines: tuple[ArabicLossLine, ...]
    total_amount: DecimalAmount
    currency: Currency
    generated_at: IsoDate

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_label_ar(self) -> str:
        return ARABIC_TOTAL_LABEL

    @computed_field  # type: ignore[prop-decorator]
    @property
    def period_label_ar(self) -> str:
        return ARABIC_PERIOD_LABEL

    @model_validator(mode="after")
    def _total_matches_lines(self) -> "ArabicLossCalculation":
        if not self.lines:
            raise ValueError("at least one loss line is required")
        computed = sum(Decimal(line.amount) for line in self.lines)
        if Decimal(self.total_amount) != computed:
            raise ValueError(
                "total_amount must equal the sum of lines' amounts"
            )
        if any(line.currency != self.currency for line in self.lines):
            raise ValueError("every line must share the top-level currency")
        return self


# ---------------------------------------------------------------------------
# The SEnA Request for Assistance (RFA) — filled fields.
# ---------------------------------------------------------------------------

#: The form title as displayed: the office-facing name plus the exact
#: current form identifier this module was verified against (issue #46
#: acceptance criterion: "SEnA form fields verified against the
#: published source" — see CIT_SENA_RFA in sena_form.py for the source).
SENA_FORM_TITLE = (
    "DOLE Single-Entry Approach (SEnA) Request for Assistance (RFA) — "
    "SEnA-2024-01 Request for Single Entry Assistance Application"
)
SENA_FILING_NOTE = (
    "Filable from abroad via MWO/POLO, the DOLE ARMS online portal, or a "
    "Special Power of Attorney (SPA) representative in the Philippines."
)


class RespondingPartyRole(str, Enum):
    EMPLOYER = "employer"
    RECRUITMENT_AGENCY = "recruitment_agency"


class RespondingParty(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    role: RespondingPartyRole
    address: Optional[str] = None
    contact: Optional[str] = None


class NatureOfRequest(str, Enum):
    """SEnA's own scope (issue #46's VENUE_SCOPE_MISMATCH check mirrors
    this at the free-text layer): money claims and illegal dismissal.
    Physical danger, passport withholding, and exit-blocking are NOT
    members — SEnA cannot hear them, so they can never populate this
    field."""

    MONEY_CLAIMS = "money_claims"
    ILLEGAL_DISMISSAL = "illegal_dismissal"


class ReliefSought(str, Enum):
    PAYMENT_OF_CLAIMS = "payment_of_claims"
    OTHER = "other"


class SenaRfaFields(BaseModel):
    """The filled RFA — field list verified against the published DOLE
    SEnA RFA form (see :mod:`app.complaint.sena_form`'s citation)."""

    model_config = ConfigDict(frozen=True)

    form_title: Literal[
        "DOLE Single-Entry Approach (SEnA) Request for Assistance (RFA) — "
        "SEnA-2024-01 Request for Single Entry Assistance Application"
    ] = SENA_FORM_TITLE
    requesting_party_name: str
    requesting_party_sex: Optional[Sex] = None
    requesting_party_address: Optional[str] = None
    requesting_party_contact: Optional[str] = None
    responding_parties: tuple[RespondingParty, ...]
    nature_of_request: tuple[NatureOfRequest, ...]
    relief_sought: tuple[ReliefSought, ...]
    supporting_documents: tuple[str, ...] = ()
    filing_note: Literal[
        "Filable from abroad via MWO/POLO, the DOLE ARMS online portal, or "
        "a Special Power of Attorney (SPA) representative in the "
        "Philippines."
    ] = SENA_FILING_NOTE
    source: Citation

    @model_validator(mode="after")
    def _non_empty(self) -> "SenaRfaFields":
        if not self.responding_parties:
            raise ValueError("at least one responding party is required")
        if not self.nature_of_request:
            raise ValueError(
                "nature_of_request must not be empty — SEnA has nothing "
                "sourced to hear for the grievances given"
            )
        return self


# ---------------------------------------------------------------------------
# FormDraft / ComplaintDraftOut — the specialist's typed output.
# ---------------------------------------------------------------------------


class IntakeNarrative(BaseModel):
    """The structured MWO/ATN intake narrative (issue #46): chronology,
    parties, amounts, and remedies — the four sections issue #46 asks
    for, each its own field so the UI can render them separately and
    ``safety_review`` scans the narrative as a whole. Model-authored
    prose in English; never Arabic (the Arabic deliverable is the
    arithmetic loss calculation only, structurally separate)."""

    model_config = ConfigDict(frozen=True)

    chronology: str
    parties: str
    amounts: str
    remedies: str

    @field_validator("chronology", "parties", "amounts", "remedies")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("every narrative section is required")
        return value

    @property
    def combined_text(self) -> str:
        """All four sections joined — what ``safety_review`` scans."""
        return "\n\n".join(
            (self.chronology, self.parties, self.amounts, self.remedies)
        )


class FormDraft(BaseModel):
    """COMPLAINT_DRAFTER's positive outcome: fills, never submits.

    No field here (or anywhere transitively under it) names a submission
    endpoint or a "submitted" status — there is no such code path in this
    module at all.
    """

    model_config = ConfigDict(frozen=True)

    sena_rfa: SenaRfaFields
    #: Base64-encoded PDF bytes from ``render_pdf`` — the UI renders it,
    #: DISPATCHER never repeats its content as prose (voice integrity).
    sena_rfa_pdf_base64: str
    intake_narrative_en: IntakeNarrative
    arabic_loss_calculation: Optional[ArabicLossCalculation] = None
    red_team: RedTeamResult

    @model_validator(mode="after")
    def _only_cleared_drafts_ship(self) -> "FormDraft":
        if not self.red_team.cleared:
            raise ValueError(
                "a FormDraft may only carry a red-team-CLEARED review"
            )
        return self


class ComplaintDraftOut(BaseModel):
    """Exactly one of ``draft``, ``illegal_recruitment_refusal``, or
    ``premature_filing_refusal`` — the drafter cannot half-refuse
    (mirrors FilingSequencerOut's discipline of exactly-one-of-N)."""

    draft: Optional[FormDraft] = None
    illegal_recruitment_refusal: Optional[IllegalRecruitmentRefusal] = None
    premature_filing_refusal: Optional[PrematureFilingRefusal] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "ComplaintDraftOut":
        members = (
            self.draft,
            self.illegal_recruitment_refusal,
            self.premature_filing_refusal,
        )
        if sum(member is not None for member in members) != 1:
            raise ValueError(
                "exactly one of draft, illegal_recruitment_refusal, or "
                "premature_filing_refusal must be set"
            )
        return self
