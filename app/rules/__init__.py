"""Jurisdiction rules corpus (issue #36, PRD #34) — assembly and selection.

The corpus is the product's critical path (ADR-0004). SA and QA are hard
commitments and ship rows; KW and AE are HELD — explicitly no rows, so a
sequencer selecting over a HELD jurisdiction gets nothing and must fall
back to the fixed refusal / Safe Floor path.

Consumption (no transformation needed)::

    from app.rules import rules_for, jurisdiction_status, RULES_CORPUS
    rows = rules_for(Jurisdiction.QA, Grievance.UNPAID_WAGES,
                     TenureBucket.EMPLOYED_IN_COUNTRY)
"""

from __future__ import annotations

from app.rules.rows_qa import QA_RULE_ROWS
from app.rules.rows_sa import SA_RULE_ROWS
from app.rules.schema import (
    ActionClass,
    Citation,
    Deadline,
    FilingTiming,
    Grievance,
    HardDeadline,
    Jurisdiction,
    JurisdictionStatus,
    ReportedDeadline,
    RuleRow,
    SourceTier,
    TenureBucket,
    Warning,
)

__all__ = [
    "ActionClass",
    "Citation",
    "Deadline",
    "FilingTiming",
    "Grievance",
    "HardDeadline",
    "Jurisdiction",
    "JurisdictionStatus",
    "JURISDICTION_STATUS",
    "ReportedDeadline",
    "RuleRow",
    "RULES_CORPUS",
    "SourceTier",
    "TenureBucket",
    "Warning",
    "jurisdiction_status",
    "rules_for",
]

#: KW and AE are HELD (issue #36 / PRD #34): no rows exist for them and
#: none may be added until sourced to at least Tier-2.
JURISDICTION_STATUS: dict[Jurisdiction, JurisdictionStatus] = {
    Jurisdiction.SA: JurisdictionStatus.ACTIVE,
    Jurisdiction.QA: JurisdictionStatus.ACTIVE,
    Jurisdiction.KW: JurisdictionStatus.HELD,
    Jurisdiction.AE: JurisdictionStatus.HELD,
}

RULES_CORPUS: tuple[RuleRow, ...] = QA_RULE_ROWS + SA_RULE_ROWS


def _validate_corpus(rows: tuple[RuleRow, ...]) -> None:
    seen: set[str] = set()
    for row in rows:
        if row.row_id in seen:
            raise ValueError(f"duplicate row_id {row.row_id!r}")
        seen.add(row.row_id)
        if JURISDICTION_STATUS[row.jurisdiction] is not JurisdictionStatus.ACTIVE:
            raise ValueError(
                f"row {row.row_id!r}: jurisdiction "
                f"{row.jurisdiction.value} is HELD and may not have rows"
            )


_validate_corpus(RULES_CORPUS)


def jurisdiction_status(jurisdiction: Jurisdiction) -> JurisdictionStatus:
    """Whether a jurisdiction has rule rows (ACTIVE) or is HELD."""
    return JURISDICTION_STATUS[jurisdiction]


def rules_for(
    jurisdiction: Jurisdiction,
    grievance: Grievance,
    tenure: TenureBucket,
) -> tuple[RuleRow, ...]:
    """Rows for one (jurisdiction x grievance x tenure) cell.

    Returns an empty tuple for HELD jurisdictions and for cells with no
    sourced row — an empty result means "no verified rule", never "no
    obligation"; callers must route to the Safe Floor, not invent a step.
    """
    return tuple(
        row
        for row in RULES_CORPUS
        if row.jurisdiction is jurisdiction
        and row.grievance is grievance
        and row.tenure is tenure
    )
