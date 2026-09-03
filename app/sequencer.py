"""FILING_SEQUENCER: verified Plan with an output gate (issue #42, ADR-0006).

Pure-function core the specialist chooses over — no model call in this
module. Consumes ``RuleRow`` objects from ``app.rules`` directly (no
transformation layer), per issue #36/#42.

Pipeline, in the order FILING_SEQUENCER is meant to call them:

1. ``jurisdiction_rules`` — is this jurisdiction ACTIVE or HELD.
2. ``sequence_actions`` — the ordered ``RuleRow`` sequence for one
   (country, tenure, grievances) input. RAISES ``JurisdictionHeldError``
   for HELD jurisdictions (KW, AE) and ``NoVerifiedPlanError`` when the
   corpus has no sourced row for any requested grievance — an empty
   result is never invented into a step.
3. ``compute_deadlines`` — attaches ``expires_at`` from each row's
   ``HardDeadline``; a ``ReportedDeadline`` never becomes a countdown
   (ADR-0005) so its step carries no ``expires_at``.
4. ``verify_plan`` — the output gate (ADR-0006): a pure structural check
   over a built :class:`Plan`. Never mutates, never re-derives content.
5. ``publish_plan`` — refuses any :class:`Plan` whose hash
   ``verify_plan`` has not cleared, including a plan tampered with after
   verification (the hash is recomputed from the plan's own content).

Staleness (hash-vs-input-hash, step expiry, DONE-survives-regeneration) is
issue #43's scope; this module carries the ``input_hash`` field so that
work has something to compare against, nothing more.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.directory import Country, resolve_keys
from app.rules import (
    ActionClass,
    Citation,
    Grievance,
    HardDeadline,
    Jurisdiction,
    JurisdictionStatus,
    RuleRow,
    SourceTier,
    TenureBucket,
    Warning,
    jurisdiction_status,
    rules_for,
)

__all__ = [
    "SequencerIn",
    "StepStatus",
    "PlanStep",
    "Plan",
    "VerifyResult",
    "JurisdictionHeldError",
    "NoVerifiedPlanError",
    "PlanNotVerifiedError",
    "GRIEVANCE_PRIORITY",
    "input_hash",
    "jurisdiction_rules",
    "sequence_actions",
    "compute_deadlines",
    "build_plan",
    "verify_plan",
    "plan_hash",
    "publish_plan",
    "held_refusal_card",
]

# ---------------------------------------------------------------------------
# SequencerIn — closed-enum input_schema (no free-text fields anywhere).
# ---------------------------------------------------------------------------


class SequencerIn(BaseModel):
    """FILING_SEQUENCER's ``input_schema``: typed args, no conversation.

    Every field is a closed enum derived from the rules corpus — "Riyadh"
    does not validate as a country; only the four corpus jurisdiction
    codes do. ``grievances`` is a non-empty tuple so at least one
    grievance is always requested.
    """

    model_config = ConfigDict(frozen=True)

    country: Jurisdiction
    tenure: TenureBucket
    grievances: tuple[Grievance, ...]

    @field_validator("grievances")
    @classmethod
    def _non_empty(cls, value: tuple[Grievance, ...]) -> tuple[Grievance, ...]:
        if not value:
            raise ValueError("grievances must contain at least one value")
        return value


def input_hash(seq_in: SequencerIn) -> str:
    """A stable hash of the ``SequencerIn`` a Plan was built from.

    Canonical JSON (sorted keys) so field order never changes the hash —
    only content does. Staleness mechanics that consume this (issue #43)
    just need this to be equal for equal inputs and unequal otherwise.
    """
    payload = json.dumps(seq_in.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Plan shape (ADR-0006, verbatim from the grilling session).
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    VOIDED = "VOIDED"


class PlanStep(BaseModel):
    """One step of a Plan. Every step shows its citation (PRD #42)."""

    model_config = ConfigDict(frozen=True)

    id: str
    status: StepStatus = StepStatus.PENDING
    rule_citation: Citation
    expires_at: Optional[str] = None
    #: Not in the ADR-0006 shape but needed to render the step at all:
    #: which grievance/venue/tier register it belongs to, its confirm-first
    #: content, and its warnings — all carried straight from the RuleRow.
    grievance: Grievance
    file_where: str
    action_class: ActionClass
    tier: SourceTier
    confirm_first_notes: tuple[str, ...] = ()
    warnings: tuple[Warning, ...] = ()
    notes: tuple[str, ...] = ()


class Plan(BaseModel):
    """Plan{plan_id, version, input_hash, steps[...]} — ADR-0006 verbatim."""

    model_config = ConfigDict(frozen=True)

    plan_id: str
    version: int
    input_hash: str
    steps: tuple[PlanStep, ...]


# ---------------------------------------------------------------------------
# Refusal exceptions.
# ---------------------------------------------------------------------------


class JurisdictionHeldError(Exception):
    """Raised by ``sequence_actions`` for a HELD jurisdiction (KW, AE).

    No sequence exists to emit; the caller must render the fixed,
    non-model refusal (``held_refusal_card``), never invent one.
    """

    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self.jurisdiction = jurisdiction
        super().__init__(
            f"{jurisdiction.value} is a HELD jurisdiction: no verified "
            "filing sequence exists"
        )


class NoVerifiedPlanError(Exception):
    """Raised by ``sequence_actions`` when no requested grievance has a
    sourced row for this (jurisdiction, tenure) cell — an empty
    ``rules_for`` result means no verified rule, never zero obligation."""


class PlanNotVerifiedError(Exception):
    """Raised by ``publish_plan``: the output gate refusing an unverified
    or tampered plan hash."""


# ---------------------------------------------------------------------------
# jurisdiction_rules
# ---------------------------------------------------------------------------


def jurisdiction_rules(jurisdiction: Jurisdiction) -> JurisdictionStatus:
    """Whether ``jurisdiction`` is ACTIVE (has rule rows) or HELD."""
    return jurisdiction_status(jurisdiction)


# ---------------------------------------------------------------------------
# sequence_actions
# ---------------------------------------------------------------------------

#: Fixed filing-order priority across grievances requested in one Plan:
#: safety first (physical danger, then a status-retaliation report that
#: can end in deportation), then the document/money claims that filing
#: before departure protects, with exit timing last — every sourced row
#: agrees the filing order matters most before any departure step.
GRIEVANCE_PRIORITY: tuple[Grievance, ...] = (
    Grievance.PHYSICAL_ABUSE_OR_DANGER,
    Grievance.STATUS_RETALIATION,
    Grievance.PASSPORT_WITHHELD,
    Grievance.UNPAID_WAGES,
    Grievance.EXIT_BLOCKED,
)


def sequence_actions(seq_in: SequencerIn) -> tuple[RuleRow, ...]:
    """The ordered ``RuleRow`` sequence for one sequencer input.

    Pure function. RAISES ``JurisdictionHeldError`` for KW/AE — sequence
    ordering never proceeds under a HELD jurisdiction. RAISES
    ``NoVerifiedPlanError`` when the corpus has no sourced row for any of
    the requested grievances in this (jurisdiction, tenure) cell — the
    caller must route to the Safe Floor, never invent a step.
    """
    if jurisdiction_status(seq_in.country) is JurisdictionStatus.HELD:
        raise JurisdictionHeldError(seq_in.country)

    requested = set(seq_in.grievances)
    ordered_grievances = [g for g in GRIEVANCE_PRIORITY if g in requested]
    # Any requested grievance outside the fixed priority tuple (should not
    # happen given the closed enum, but fail closed rather than drop it
    # silently) is appended in its original order.
    ordered_grievances.extend(
        g for g in seq_in.grievances if g not in GRIEVANCE_PRIORITY
    )

    rows: list[RuleRow] = []
    for grievance in ordered_grievances:
        rows.extend(rules_for(seq_in.country, grievance, seq_in.tenure))

    if not rows:
        raise NoVerifiedPlanError(
            f"no sourced rule row for {seq_in.country.value} / "
            f"{seq_in.tenure.value} / "
            f"{[g.value for g in seq_in.grievances]}"
        )
    return tuple(rows)


# ---------------------------------------------------------------------------
# compute_deadlines
# ---------------------------------------------------------------------------


def compute_deadlines(
    rows: tuple[RuleRow, ...], *, now: datetime
) -> tuple[PlanStep, ...]:
    """Builds ``PlanStep`` objects from rows, attaching ``expires_at``.

    Pure function. Only a ``HardDeadline`` (Tier-1 only, per schema)
    becomes an ``expires_at`` countdown; a ``ReportedDeadline`` (Tier-2,
    reported-not-relied-upon) never does (ADR-0005) — its step's
    ``expires_at`` stays ``None`` and the reported text rides in ``notes``.
    """
    steps: list[PlanStep] = []
    for row in rows:
        expires_at: Optional[str] = None
        notes = tuple(row.notes)
        if isinstance(row.deadline, HardDeadline):
            expires_at = (
                now + timedelta(days=row.deadline.duration_days)
            ).isoformat()
        elif row.deadline is not None:
            # ReportedDeadline: reported-not-relied-upon, never a countdown.
            notes = (row.deadline.reported_text,) + notes
        steps.append(
            PlanStep(
                id=row.row_id,
                rule_citation=row.citation,
                expires_at=expires_at,
                grievance=row.grievance,
                file_where=row.file_where,
                action_class=row.action_class,
                tier=row.tier,
                confirm_first_notes=row.confirm_first_notes,
                warnings=row.warnings,
                notes=notes,
            )
        )
    return tuple(steps)


def build_plan(
    seq_in: SequencerIn,
    steps: tuple[PlanStep, ...],
    *,
    plan_id: str,
    version: int = 1,
) -> Plan:
    """Assembles a :class:`Plan` from computed steps. Pure; no I/O."""
    return Plan(
        plan_id=plan_id,
        version=version,
        input_hash=input_hash(seq_in),
        steps=steps,
    )


# ---------------------------------------------------------------------------
# verify_plan — the output gate's pure check (ADR-0006).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    violations: tuple[str, ...]


def verify_plan(plan: Plan) -> VerifyResult:
    """The output gate's pure check: citation-presence, not tier (ADR-0006).

    ``verify_plan`` enforces that every step is cited and structurally
    sound; tier bounds (Tier-2 may not assert a hard deadline or direct an
    irreversible action) are already unrepresentable at the schema level
    (``RuleRow``), but a defensive re-check rides here too since a
    ``Plan``/``PlanStep`` is a separate, independently constructible
    object. Never mutates the plan and never re-derives its content.
    """
    violations: list[str] = []

    if not plan.steps:
        violations.append("plan has no steps")

    ids = [step.id for step in plan.steps]
    if len(ids) != len(set(ids)):
        violations.append("duplicate step ids")

    for step in plan.steps:
        if not step.rule_citation.source_name.strip():
            violations.append(f"{step.id}: missing citation source_name")
        if not step.rule_citation.reference.strip():
            violations.append(f"{step.id}: missing citation reference")
        if not step.rule_citation.url.startswith("http"):
            violations.append(f"{step.id}: citation url is not a real link")
        if (
            step.tier is SourceTier.TIER_2
            and step.action_class is ActionClass.IRREVERSIBLE
        ):
            violations.append(
                f"{step.id}: Tier-2 step directs an irreversible action"
            )
        if step.tier is SourceTier.TIER_2 and step.expires_at is not None:
            violations.append(
                f"{step.id}: Tier-2 step carries a hard-deadline countdown"
            )

    return VerifyResult(ok=not violations, violations=tuple(violations))


def plan_hash(plan: Plan) -> str:
    """A stable hash of a plan's own content — the hash ``publish_plan``
    checks against the set ``verify_plan`` cleared. Any change to the
    plan's steps (a tamper) changes this hash."""
    return hashlib.sha256(
        plan.model_dump_json().encode("utf-8")
    ).hexdigest()


def publish_plan(plan: Plan, *, cleared_hashes: frozenset[str]) -> Plan:
    """The output gate itself: refuses any plan hash not in ``cleared_hashes``.

    ``cleared_hashes`` is populated by the caller only after calling
    ``verify_plan`` and getting ``ok=True`` for this exact plan — never
    for a plan re-derived or mutated afterwards. Recomputing the hash
    here (rather than trusting a flag on the object) is what makes a
    tampered plan — one edited after verification — refuse: its content
    hash no longer matches anything ``verify_plan`` cleared.
    """
    result = verify_plan(plan)
    if not result.ok:
        raise PlanNotVerifiedError(
            f"plan {plan.plan_id!r} failed verify_plan: {result.violations}"
        )
    current_hash = plan_hash(plan)
    if current_hash not in cleared_hashes:
        raise PlanNotVerifiedError(
            f"plan {plan.plan_id!r} hash {current_hash!r} was not cleared "
            "by verify_plan — refusing to publish"
        )
    return plan


# ---------------------------------------------------------------------------
# HELD jurisdiction refusal: fixed, non-model, code-owned (issue #42).
# ---------------------------------------------------------------------------

#: Directory keys for the HELD-jurisdiction refusal card: the country's
#: MWO plus the OWWA/DMW hotline. Resolved and dialability-filtered
#: server-side, same discipline as app.safe_floor.
HELD_REFUSAL_KEYS: dict[Country, tuple[str, ...]] = {
    Country.KW: ("mwo_kuwait", "owwa_1348"),
    Country.AE: ("mwo_dubai", "mwo_abu_dhabi", "owwa_1348"),
}

_HELD_COUNTRY_LABEL: dict[Country, str] = {
    Country.KW: "Kuwait",
    Country.AE: "the UAE",
}


def held_refusal_card(jurisdiction: Jurisdiction) -> dict[str, Any]:
    """The fixed, code-owned refusal for a HELD jurisdiction.

    Never composed by the model: the MWO directory for the country, the
    OWWA/DMW hotline (1348), and the fixed line "we do not yet have a
    verified filing order for [country]; do not leave before speaking to
    the MWO". Frame it in DISPATCHER's own words is not offered here —
    unlike ``safe_floor_card`` this text ships as-is, since ADR-0006 treats
    an uncited plan under a verified-looking UI as worse than none.
    """
    country = Country(jurisdiction.value)
    keys = HELD_REFUSAL_KEYS.get(country, ("owwa_1348",))
    label = _HELD_COUNTRY_LABEL.get(country, country.value)
    return {
        "type": "held_refusal",
        "country": country.value,
        "contacts": resolve_keys(list(keys), country),
        # Verbatim from the task's fixed refusal framing (issue #42):
        # "we do not yet have a verified filing order for [country]; do
        # not leave before speaking to the MWO" — only the leading
        # capital and the trailing period are added for sentence case.
        "message": (
            f"We do not yet have a verified filing order for {label}; "
            "do not leave before speaking to the MWO."
        ),
    }
