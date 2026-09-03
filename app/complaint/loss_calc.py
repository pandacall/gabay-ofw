"""``compute_wage_loss`` (issue #46, PRD #34): the Arabic deliverable is
the arithmetic loss calculation ONLY — the artifact the ILO Qatar worker
guide tells her to bring, with no tool anywhere to make it.

Pure arithmetic, no model: monthly salary x months unpaid, plus any
additive claim lines (unpaid overtime, withheld final pay, unpaid
benefits, an unreturned placement fee), summed to a total. Every amount
and date is already pattern-constrained at the schema boundary
(:mod:`app.complaint.schema`); this module only ever does the sum.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from app.complaint.schema import (
    ArabicLossCalculation,
    ArabicLossLine,
    ArabicLossLineLabel,
    WageLossInput,
)


def compute_wage_loss(
    wage_loss: WageLossInput, *, now: datetime.date | None = None
) -> ArabicLossCalculation:
    """Builds the arithmetic-only loss calculation from typed input.

    Pure: given the same ``wage_loss`` and ``now``, always returns the
    same result. ``now`` defaults to today (UTC) and only ever stamps
    ``generated_at`` — it never enters the arithmetic.
    """
    generated_at = (now or datetime.datetime.now(datetime.timezone.utc).date())

    base = ArabicLossLine(
        label=ArabicLossLineLabel.MONTHLY_SALARY,
        amount=str(
            Decimal(wage_loss.monthly_salary) * wage_loss.months_unpaid
        ),
        currency=wage_loss.currency,
    )
    lines: list[ArabicLossLine] = [base]
    for other in wage_loss.other_claims:
        lines.append(
            ArabicLossLine(
                label=ArabicLossLineLabel(other.label.value),
                amount=other.amount,
                currency=wage_loss.currency,
            )
        )

    total = sum(Decimal(line.amount) for line in lines)
    return ArabicLossCalculation(
        period_start=wage_loss.period_start,
        period_end=wage_loss.period_end,
        lines=tuple(lines),
        total_amount=str(total),
        currency=wage_loss.currency,
        generated_at=generated_at.isoformat(),
    )
