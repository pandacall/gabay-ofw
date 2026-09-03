"""``compute_wage_loss`` arithmetic tests (issue #46): the Arabic
deliverable's arithmetic core. Pure, no model.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from app.complaint.loss_calc import compute_wage_loss
from app.complaint.schema import (
    ArabicLossLineLabel,
    OtherClaimAmount,
    OtherClaimLabel,
    WageLossInput,
)


class TestBaseArithmetic:
    def test_monthly_salary_times_months_unpaid(self):
        wage_loss = WageLossInput(
            monthly_salary="1500.00",
            currency="SAR",
            months_unpaid=3,
            period_start="2026-01-01",
            period_end="2026-04-01",
        )
        calc = compute_wage_loss(wage_loss, now=datetime.date(2026, 6, 1))
        assert Decimal(calc.total_amount) == Decimal("4500.00")
        (line,) = calc.lines
        assert line.label is ArabicLossLineLabel.MONTHLY_SALARY
        assert Decimal(line.amount) == Decimal("4500.00")
        assert calc.generated_at == "2026-06-01"

    def test_period_dates_carry_through(self):
        wage_loss = WageLossInput(
            monthly_salary="1000",
            currency="QAR",
            months_unpaid=2,
            period_start="2026-02-01",
            period_end="2026-04-01",
        )
        calc = compute_wage_loss(wage_loss, now=datetime.date(2026, 5, 1))
        assert calc.period_start == "2026-02-01"
        assert calc.period_end == "2026-04-01"


class TestAdditiveClaimLines:
    def test_other_claims_are_summed_into_the_total(self):
        wage_loss = WageLossInput(
            monthly_salary="1000",
            currency="SAR",
            months_unpaid=2,
            period_start="2026-01-01",
            period_end="2026-03-01",
            other_claims=(
                OtherClaimAmount(
                    label=OtherClaimLabel.UNPAID_OVERTIME, amount="150.50"
                ),
                OtherClaimAmount(
                    label=OtherClaimLabel.UNRETURNED_PLACEMENT_FEE, amount="300"
                ),
            ),
        )
        calc = compute_wage_loss(wage_loss, now=datetime.date(2026, 4, 1))
        # 1000*2 + 150.50 + 300 = 2450.50
        assert Decimal(calc.total_amount) == Decimal("2450.50")
        assert len(calc.lines) == 3

    def test_every_line_shares_the_top_level_currency(self):
        wage_loss = WageLossInput(
            monthly_salary="1000",
            currency="AED",
            months_unpaid=1,
            period_start="2026-01-01",
            period_end="2026-02-01",
            other_claims=(
                OtherClaimAmount(
                    label=OtherClaimLabel.UNPAID_BENEFITS, amount="50"
                ),
            ),
        )
        calc = compute_wage_loss(wage_loss, now=datetime.date(2026, 3, 1))
        assert all(line.currency.value == "AED" for line in calc.lines)
        assert calc.currency.value == "AED"
