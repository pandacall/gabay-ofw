"""Schema for the jurisdiction rules corpus (issue #36, PRD #34).

Rule rows are the data FILING_SEQUENCER selects over: for each
(grievance x tenure situation) in an active jurisdiction — file where,
before or after leaving, with what deadline. Every row carries a citation
and a Source Tier per ADR-0005: tier bounds what a row may authorize, by
reversibility.

- Tier-1 (statute, official government guidance, ILO material published
  under an agreement with the government) may assert hard dates and direct
  irreversible actions.
- Tier-2 (reputable NGO / ILO analysis) may only direct protective
  reversible steps, states dates as reported-not-relied-upon, and ships
  warnings at full strength. It is never the sole basis for an
  irreversible move.

The tier bounds are enforced structurally by validators below: a Tier-2
row carrying a :class:`HardDeadline` or directing an ``IRREVERSIBLE``
action is unrepresentable, not merely discouraged.

``sequence_actions`` / ``verify_plan`` consume :class:`RuleRow` objects
directly — no transformation layer.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, model_validator


class SourceTier(str, Enum):
    """ADR-0005 source tier. Bounds authorization by reversibility."""

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"


class Jurisdiction(str, Enum):
    SA = "SA"
    QA = "QA"
    KW = "KW"
    AE = "AE"


class JurisdictionStatus(str, Enum):
    """ACTIVE jurisdictions have rule rows; HELD ones ship a fixed refusal."""

    ACTIVE = "active"
    HELD = "held"


class Grievance(str, Enum):
    """Grievance types the corpus branches on.

    Values exist only because sourced rows actually branch on them — see
    docs/rules-corpus.md for the derivation table. Do not add a value
    without a sourced row whose (venue, timing, deadline, warnings)
    differ from every existing value's rows.
    """

    #: Money claims: unpaid/underpaid wages and end-of-service benefits.
    #: (One value: wages and EOSB share venue, timing, and deadline in
    #: every sourced row — splitting them would be invented granularity.)
    UNPAID_WAGES = "unpaid_wages"
    #: Employer withholds passport / travel documents.
    PASSPORT_WITHHELD = "passport_withheld"
    #: Physical abuse or serious danger to life or health.
    PHYSICAL_ABUSE_OR_DANGER = "physical_abuse_or_danger"
    #: Employer-initiated immigration-status action: QID cancellation
    #: before a job change (QA), absconding/huroob report (SA).
    STATUS_RETALIATION = "status_retaliation"
    #: Worker wants or needs to leave the country and exit is obstructed
    #: or its timing interacts with a claim.
    EXIT_BLOCKED = "exit_blocked"


class TenureBucket(str, Enum):
    """Tenure situations the corpus branches on.

    Derived from rows, not guessed: length-of-service distinctions
    (probation, one-year EOSB vesting) change entitlement amounts, not
    where/when to file, so they are deliberately NOT buckets. See
    docs/rules-corpus.md.
    """

    #: Still with the employer, still in the country.
    EMPLOYED_IN_COUNTRY = "employed_in_country"
    #: Has left (or is about to leave) the employer but is still in the
    #: country. The bucket where filing order versus flight matters most.
    LEFT_EMPLOYER_IN_COUNTRY = "left_employer_in_country"
    #: Has left the country.
    DEPARTED_COUNTRY = "departed_country"


class FilingTiming(str, Enum):
    """Whether this row's filing step happens before or after leaving."""

    BEFORE_LEAVING_COUNTRY = "before_leaving_country"
    FROM_ABROAD = "from_abroad"


class ActionClass(str, Enum):
    """Reversibility of the step a row directs (ADR-0005 boundary)."""

    PROTECTIVE_REVERSIBLE = "protective_reversible"
    IRREVERSIBLE = "irreversible"


class Citation(BaseModel):
    """A verifiable source reference. ``tier`` classifies the source itself."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    reference: str
    url: str
    tier: SourceTier


class HardDeadline(BaseModel):
    """A deadline that may be asserted and rendered as a countdown.

    Only representable on Tier-1 rows (enforced by :class:`RuleRow`).
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["hard"] = "hard"
    duration_days: int
    #: The event the clock runs from, stated precisely.
    starts_from: str


class ReportedDeadline(BaseModel):
    """A deadline stated as reported-not-relied-upon (ADR-0005 Tier-2).

    Rendered as a report with a confirm-first instruction, never a
    countdown.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["reported"] = "reported"
    reported_text: str
    #: Who must confirm before the date is relied on (e.g. the MWO).
    confirm_with: str


Deadline = Union[HardDeadline, ReportedDeadline]


class Warning(BaseModel):
    """A warning attached to a row.

    Warnings ship at full strength regardless of tier (ADR-0005): being
    wrong about a warning only makes the user more careful.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    citation: Citation


class RuleRow(BaseModel):
    """One (jurisdiction x grievance x tenure) rule: file where, when,
    with what deadline — cited and tier-bounded."""

    model_config = ConfigDict(frozen=True)

    row_id: str
    jurisdiction: Jurisdiction
    grievance: Grievance
    tenure: TenureBucket
    #: Venue and channel, with official names kept untranslated
    #: (PRD: office names and legal terms are never translated).
    file_where: str
    filing_timing: FilingTiming
    action_class: ActionClass
    deadline: Optional[Deadline] = None
    #: Primary citation for the row's instruction. ``tier`` on the row is
    #: the register the row ships at; it may be a deliberate downgrade of
    #: a stronger citation, never an upgrade of a weaker one.
    citation: Citation
    tier: SourceTier
    warnings: tuple[Warning, ...] = ()
    #: Tier-2 confirm-first content: facts that must be confirmed with the
    #: named authority before being acted on. Never rendered as countdowns.
    confirm_first_notes: tuple[str, ...] = ()
    #: Supporting process detail (durations of official process stages,
    #: practical channels). Informational register only.
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _enforce_tier_bounds(self) -> "RuleRow":
        if self.tier is SourceTier.TIER_2:
            if isinstance(self.deadline, HardDeadline):
                raise ValueError(
                    f"row {self.row_id!r}: a Tier-2 row may not assert a "
                    "hard deadline (ADR-0005: dates are "
                    "reported-not-relied-upon below Tier-1)"
                )
            if self.action_class is ActionClass.IRREVERSIBLE:
                raise ValueError(
                    f"row {self.row_id!r}: a Tier-2 row may not direct an "
                    "irreversible action (ADR-0005)"
                )
        if (
            self.tier is SourceTier.TIER_1
            and self.citation.tier is not SourceTier.TIER_1
        ):
            raise ValueError(
                f"row {self.row_id!r}: a Tier-1 row must rest on a Tier-1 "
                "citation — a row may downgrade its source's tier, never "
                "upgrade it"
            )
        return self
