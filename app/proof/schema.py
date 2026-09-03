"""Typed boundary of PROOF_BUILDER (issue #45, PRD #34).

PROOF_BUILDER is a single-turn specialist: it sees NONE of the
conversation. Its entire input is :class:`BundleState` (typed args) plus
session state; its entire output is :class:`ProofGap`. Everything the
safety story depends on is structural, not prompted:

* **No free text in.** Every string field anywhere under
  :class:`BundleState` is an enum, a bool, or a pattern-constrained
  scalar (a decimal amount or an ISO date). :class:`DocFacts` — the shape
  through which OCR'd document facts enter — has NO free-text field, so
  injected employer text ("ignore your instructions", "call the police")
  is unrepresentable. Unknown keys are silently dropped; a declared field
  carrying a value that fails its constraint is DROPPED, never echoed
  back in a validation error (pydantic errors quote input values, which
  would smuggle the injected prose to DISPATCHER).

* **One ask per turn.** ``next_ask`` is a single object, not a list.

* **The scope limit is said to her.** ``scope_limit`` is a ``Literal``
  of exactly one string — "this is what the office will ask you for" —
  so a ProofGap that does not carry the line fails schema validation.
  "This will win your case" is unrepresentable.

* **Never as-if-proven.** An artifact declared an unclosed gap may not
  also appear in ``satisfied``; an insufficient bundle must carry a next
  ask or state its unclosed gaps — silently proceeding is invalid.

Checklist rows (:class:`ChecklistRow`) reuse ``Citation`` /
``SourceTier`` from :mod:`app.rules.schema` so every row records a
source and an ADR-0005 tier.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter, model_validator

from app.rules.schema import Citation, SourceTier

# The scope limit, said to her in the output itself (issue #45): what the
# office will ask for — never a promise about winning.
SCOPE_LIMIT_LINE = (
    "This is what the office will ask you for. It is not a promise about "
    "the outcome of your case."
)

# Pattern-constrained scalars: the only non-enum strings that exist
# anywhere under BundleState. Nothing prose-shaped can pass them.
DecimalAmount = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,2})?$")]
IsoDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class Venue(str, Enum):
    """Intake venues whose published requirements source a checklist."""

    #: DOLE Single-Entry Approach: the SEnA Request for Assistance (RFA).
    SENA_RFA = "sena_rfa"
    #: OWWA welfare/membership programs: proof-of-employment package.
    OWWA_PROOF_OF_EMPLOYMENT = "owwa_proof_of_employment"
    #: Migrant Workers Office / Assistance-to-Nationals case intake.
    MWO_ATN_INTAKE = "mwo_atn_intake"


class ArtifactType(str, Enum):
    """Closed vocabulary of artifacts the checklists know about."""

    EMPLOYMENT_CONTRACT = "employment_contract"
    OEC = "oec"  # Overseas Employment Certificate
    PASSPORT_COPY = "passport_copy"
    RESIDENCE_ID_COPY = "residence_id_copy"  # iqama (SA) / QID (QA) / Emirates ID
    VALID_PH_ID = "valid_ph_id"
    PAYSLIP = "payslip"
    REMITTANCE_RECEIPT = "remittance_receipt"
    BANK_STATEMENT = "bank_statement"
    COMPANY_ID = "company_id"
    CHAT_SCREENSHOT = "chat_screenshot"
    PHOTO_OF_WORKPLACE = "photo_of_workplace"
    PHOTO_OF_INJURY = "photo_of_injury"
    MEDICAL_RECORD = "medical_record"
    AGENCY_RECEIPT_OR_CONTRACT = "agency_receipt_or_contract"
    OWWA_MEMBERSHIP_PROOF = "owwa_membership_proof"
    SPECIAL_POWER_OF_ATTORNEY = "special_power_of_attorney"


class ArtifactCondition(str, Enum):
    """What she actually holds — an original is not a bad phone photo."""

    ORIGINAL = "original"
    CLEAR_COPY_OR_PHOTO = "clear_copy_or_photo"
    BAD_PHOTO = "bad_photo"
    SCREENSHOT_ONLY = "screenshot_only"
    ILLEGIBLE = "illegible"


class PhoneRisk(str, Enum):
    """Capture-risk input to the ranking (risk of being caught looking)."""

    PHONE_SAFE = "phone_safe"
    PHONE_WATCHED = "phone_watched"
    MINUTES_ONLY = "minutes_only"


class Currency(str, Enum):
    SAR = "SAR"
    QAR = "QAR"
    AED = "AED"
    KWD = "KWD"
    PHP = "PHP"
    USD = "USD"


def _drop_invalid_fields(model_cls: type[BaseModel], data: Any) -> Any:
    """Drops any field value that fails its own constraint, silently.

    This is the refusal mechanism for injected OCR text: schema
    validation DROPS the offending value instead of raising, because a
    pydantic ValidationError quotes the input value — which would carry
    the injected prose back to DISPATCHER inside the error string.
    """
    if not isinstance(data, dict):
        return data
    cleaned: dict[str, Any] = {}
    for name, field in model_cls.model_fields.items():
        keys = [name] + ([field.alias] if field.alias else [])
        for key in keys:
            if key not in data:
                continue
            try:
                TypeAdapter(field.annotation).validate_python(data[key])
            except Exception:
                continue  # dropped: never echoed, never raised
            cleaned[name] = data[key]
            break
    return cleaned


def _enum_member_value(enum_cls: type[Enum], value: Any) -> Optional[str]:
    """The enum member value for ``value``, or None — never a raise that
    would quote the input."""
    raw = str(getattr(value, "value", value))
    return raw if raw in {member.value for member in enum_cls} else None


class DocFacts(BaseModel):
    """Facts read off a document. NO free-text field, by design (issue #45).

    What a document *says* is captured as booleans (is the employer's
    name visible? is there a signature?), enums, amounts, and dates.
    Prose — and therefore injected instructions inside OCR'd employer
    text — is structurally unrepresentable. Unknown keys and constraint
    failures are dropped by validation, so nothing free-text survives
    into the Case or crosses back to DISPATCHER.
    """

    model_config = ConfigDict(extra="ignore")

    doc_type: Optional[ArtifactType] = None
    legible: Optional[bool] = None
    in_arabic_only: Optional[bool] = None
    shows_worker_name: Optional[bool] = None
    shows_employer_name: Optional[bool] = None
    shows_salary: Optional[bool] = None
    shows_signature: Optional[bool] = None
    shows_official_stamp: Optional[bool] = None
    salary_amount: Optional[DecimalAmount] = None
    currency: Optional[Currency] = None
    document_date: Optional[IsoDate] = None
    period_start: Optional[IsoDate] = None
    period_end: Optional[IsoDate] = None

    @model_validator(mode="before")
    @classmethod
    def _sanitize(cls, data: Any) -> Any:
        return _drop_invalid_fields(cls, data)


class HeldArtifact(BaseModel):
    """One artifact she already has, in whatever condition."""

    model_config = ConfigDict(extra="ignore")

    artifact: ArtifactType
    condition: ArtifactCondition = ArtifactCondition.CLEAR_COPY_OR_PHOTO
    facts: Optional[DocFacts] = None


class BundleState(BaseModel):
    """PROOF_BUILDER's typed input: the whole evidence bundle as it stands.

    This is the tool's ``input_schema`` — with it declared, ADK exposes
    these typed parameters to DISPATCHER's function-calling instead of
    the banned bare ``request: string``.
    """

    model_config = ConfigDict(extra="ignore")

    venue: Venue
    artifacts_held: list[HeldArtifact] = []
    #: Artifacts she has SAID she cannot get. Asking for these again is a
    #: dead end; the plan must route around them.
    artifacts_unobtainable: list[ArtifactType] = []
    phone_risk: PhoneRisk = PhoneRisk.PHONE_SAFE

    @model_validator(mode="before")
    @classmethod
    def _sanitize(cls, data: Any) -> Any:
        """Rebuilds the input from known fields only, dropping anything
        invalid — including a poisoned ``venue`` and every unknown key —
        so no raising path (a missing-required error quotes its input)
        can carry injected prose."""
        if not isinstance(data, dict):
            return data
        cleaned: dict[str, Any] = {}
        venue = _enum_member_value(Venue, data.get("venue"))
        if venue is not None:
            cleaned["venue"] = venue
        held = data.get("artifacts_held")
        if isinstance(held, list):
            kept = []
            for item in held:
                try:
                    kept.append(HeldArtifact.model_validate(item))
                except Exception:
                    continue  # dropped, never echoed
            cleaned["artifacts_held"] = kept
        unobtainable = data.get("artifacts_unobtainable")
        if isinstance(unobtainable, list):
            cleaned["artifacts_unobtainable"] = [
                value
                for value in (
                    _enum_member_value(ArtifactType, item) for item in unobtainable
                )
                if value is not None
            ]
        risk = _enum_member_value(PhoneRisk, data.get("phone_risk"))
        if risk is not None:
            cleaned["phone_risk"] = risk
        return cleaned


class RequirementLevel(str, Enum):
    """Required-vs-strengthens, recorded per checklist row (issue #45)."""

    REQUIRED = "required"
    STRENGTHENS = "strengthens"


class ChecklistRow(BaseModel):
    """One artifact one venue's published intake asks for — with a source.

    Reviewable data, not prompt text: every row carries the published
    source it was taken from and its ADR-0005 tier.
    """

    model_config = ConfigDict(frozen=True)

    row_id: str
    venue: Venue
    artifact: ArtifactType
    requirement: RequirementLevel
    #: Obtainable substitutes for a required-but-unobtainable artifact,
    #: best first (e.g. a remittance receipt for a payslip nobody issues).
    substitutes: tuple[ArtifactType, ...] = ()
    #: What this artifact shows the office, in plain words.
    purpose: str
    source: Citation
    tier: SourceTier

    @model_validator(mode="after")
    def _tier_never_upgrades(self) -> "ChecklistRow":
        if self.tier is SourceTier.TIER_1 and self.source.tier is not SourceTier.TIER_1:
            raise ValueError(
                f"row {self.row_id!r}: a Tier-1 row must rest on a Tier-1 "
                "source — a row may downgrade its source's tier, never "
                "upgrade it (ADR-0005)"
            )
        return self


class OutstandingRow(BaseModel):
    """A checklist row the bundle does not yet cover."""

    artifact: ArtifactType
    requirement: RequirementLevel


class ArtifactAsk(BaseModel):
    """The single next-artifact ask. One per turn, structurally."""

    artifact: ArtifactType
    #: Set when this ask substitutes for a required-but-unobtainable one.
    substitute_for: Optional[ArtifactType] = None
    #: How to capture it, written for her situation (bad light, watched
    #: phone, minutes only). Specialist-authored copy — its inputs are
    #: injection-free by construction, so this cannot launder OCR text.
    how_to_capture: str
    #: Why this one first: the marginal value x obtainability x risk call.
    why_first: str


class UnclosedGap(BaseModel):
    """A gap she said she cannot close: named, with the bundle's limits."""

    artifact: ArtifactType
    #: What the bundle will and will not support without it — stated
    #: plainly, never silently treated as proven.
    bundle_limit: str


class ProofGap(BaseModel):
    """PROOF_BUILDER's typed output: the gap analysis and the one ask."""

    venue: Venue
    #: The scope limit is SAID TO HER: a Literal of exactly one string,
    #: so omitting or rephrasing it fails schema validation.
    scope_limit: Literal[
        "This is what the office will ask you for. It is not a promise "
        "about the outcome of your case."
    ]
    #: Checklist rows the bundle already covers.
    satisfied: list[ArtifactType] = []
    #: Rows still open, with their required-vs-strengthens level.
    outstanding: list[OutstandingRow] = []
    #: True when the bundle covers what the venue's intake requires: the
    #: loop's termination condition. No further ask is made.
    sufficient: bool
    #: Exactly ONE artifact ask per turn, or None on termination /
    #: re-plan-around-gaps turns.
    next_ask: Optional[ArtifactAsk] = None
    #: Gaps she said she cannot close, each with the bundle's stated
    #: limits. The plan proceeds AROUND these, never as if proven.
    unclosed_gaps: list[UnclosedGap] = []

    @model_validator(mode="after")
    def _enforce_loop_invariants(self) -> "ProofGap":
        if self.sufficient and self.next_ask is not None:
            raise ValueError(
                "a sufficient bundle terminates the loop: no next_ask"
            )
        if self.sufficient and any(
            row.requirement is RequirementLevel.REQUIRED
            for row in self.outstanding
        ):
            raise ValueError(
                "a bundle with an outstanding REQUIRED row is not "
                "sufficient — termination never papers over a required gap"
            )
        if not self.sufficient and self.next_ask is None and not self.unclosed_gaps:
            raise ValueError(
                "an insufficient bundle must carry a next_ask or state its "
                "unclosed gaps — silently proceeding is invalid"
            )
        satisfied = set(self.satisfied)
        for gap in self.unclosed_gaps:
            if gap.artifact in satisfied:
                raise ValueError(
                    f"{gap.artifact.value} is declared an unclosed gap and "
                    "satisfied at once — a gap is never treated as proven"
                )
        if self.next_ask is not None:
            if self.next_ask.artifact in satisfied:
                raise ValueError(
                    "next_ask must target an artifact the bundle lacks"
                )
            unclosed = {gap.artifact for gap in self.unclosed_gaps}
            if self.next_ask.artifact in unclosed:
                raise ValueError(
                    "next_ask may not re-ask for a gap she said she cannot "
                    "close; ask for a substitute or proceed around it"
                )
        return self
