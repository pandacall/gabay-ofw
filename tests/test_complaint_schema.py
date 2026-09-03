"""Structural tests for COMPLAINT_DRAFTER's typed boundary (issue #46).

These assert what must NOT be representable, not just what happens to
work today: no free-text Arabic generation path, no submission code path
anywhere under :mod:`app.complaint`, and the exactly-one-of-N discipline
on the specialist's output.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest
from pydantic import ValidationError

import app.complaint as complaint_package
from app.complaint.schema import (
    ArabicLossCalculation,
    ArabicLossLine,
    ArabicLossLineLabel,
    ComplaintDraftOut,
    FormDraft,
    IllegalRecruitmentRefusal,
    IntakeNarrative,
    PrematureFilingRefusal,
    RedTeamFinding,
    RedTeamResult,
    SenaRfaFields,
    RespondingParty,
    RespondingPartyRole,
    NatureOfRequest,
    ReliefSought,
)
from app.rules.schema import Citation, SourceTier

_CIT = Citation(
    source_name="test source", reference="test reference", url="https://example.test",
    tier=SourceTier.TIER_1,
)


def _narrative(**overrides) -> IntakeNarrative:
    defaults = dict(
        chronology="She worked from 2024-01-01 to 2026-06-01.",
        parties="Worker: Maria Santos. Employer: Al Rashid Household.",
        amounts="Three months unpaid at SAR 1,500 per month.",
        remedies="She requests payment of her unpaid wages.",
    )
    defaults.update(overrides)
    return IntakeNarrative(**defaults)


def _sena_fields(**overrides) -> SenaRfaFields:
    defaults = dict(
        requesting_party_name="Maria Santos",
        responding_parties=(
            RespondingParty(name="Al Rashid Household", role=RespondingPartyRole.EMPLOYER),
        ),
        nature_of_request=(NatureOfRequest.MONEY_CLAIMS,),
        relief_sought=(ReliefSought.PAYMENT_OF_CLAIMS,),
        source=_CIT,
    )
    defaults.update(overrides)
    return SenaRfaFields(**defaults)


class TestArabicDeliverableIsArithmeticOnly:
    """No field anywhere under ArabicLossCalculation can hold free text,
    in either language."""

    def test_every_field_is_an_enum_amount_or_date_never_a_bare_string(self):
        from pydantic import StringConstraints

        for model_cls in (ArabicLossLine, ArabicLossCalculation):
            for name, field in model_cls.model_fields.items():
                annotation = field.annotation
                origin = getattr(annotation, "__origin__", None)
                args = getattr(annotation, "__args__", ())
                candidates = [annotation] + list(args)
                for candidate in candidates:
                    if candidate is not str:
                        continue
                    # A bare `str` annotation is only acceptable when
                    # pydantic's own constraint metadata (from
                    # Annotated[str, StringConstraints(pattern=...)])
                    # pattern-locks it to digits/dates — never free text.
                    has_pattern = any(
                        isinstance(meta, StringConstraints) and meta.pattern
                        for meta in field.metadata
                    )
                    assert has_pattern, (
                        f"{model_cls.__name__}.{name} accepts a bare, "
                        "unconstrained str — the Arabic deliverable must "
                        "never hold free text"
                    )

    def test_arabic_label_is_a_fixed_lookup_never_model_supplied(self):
        line = ArabicLossLine(
            label=ArabicLossLineLabel.MONTHLY_SALARY, amount="1000", currency="SAR"
        )
        assert line.label_ar == "الراتب الشهري"

    def test_total_must_equal_sum_of_lines(self):
        with pytest.raises(ValidationError):
            ArabicLossCalculation(
                period_start="2026-01-01",
                period_end="2026-03-01",
                lines=(
                    ArabicLossLine(
                        label=ArabicLossLineLabel.MONTHLY_SALARY,
                        amount="1000",
                        currency="SAR",
                    ),
                ),
                total_amount="999",
                currency="SAR",
                generated_at="2026-03-01",
            )

    def test_no_lines_is_rejected(self):
        with pytest.raises(ValidationError):
            ArabicLossCalculation(
                period_start="2026-01-01",
                period_end="2026-03-01",
                lines=(),
                total_amount="0",
                currency="SAR",
                generated_at="2026-03-01",
            )


class TestOnlyClearedDraftsShip:
    def test_form_draft_refuses_an_uncleared_red_team_result(self):
        uncleared = RedTeamResult(
            cleared=False,
            findings=(
                RedTeamFinding(
                    check_id="absconding_admission", guidance="remove it"
                ),
            ),
        )
        with pytest.raises(ValidationError):
            FormDraft(
                sena_rfa=_sena_fields(),
                sena_rfa_pdf_base64="",
                intake_narrative_en=_narrative(),
                red_team=uncleared,
            )

    def test_form_draft_accepts_a_cleared_review(self):
        cleared = RedTeamResult(cleared=True)
        draft = FormDraft(
            sena_rfa=_sena_fields(),
            sena_rfa_pdf_base64="cGRm",
            intake_narrative_en=_narrative(),
            red_team=cleared,
        )
        assert draft.red_team.cleared is True


class TestExactlyOneOutcome:
    def test_none_set_is_rejected(self):
        with pytest.raises(ValidationError):
            ComplaintDraftOut()

    def test_two_set_is_rejected(self):
        cleared = RedTeamResult(cleared=True)
        draft = FormDraft(
            sena_rfa=_sena_fields(),
            sena_rfa_pdf_base64="cGRm",
            intake_narrative_en=_narrative(),
            red_team=cleared,
        )
        with pytest.raises(ValidationError):
            ComplaintDraftOut(
                draft=draft,
                premature_filing_refusal=PrematureFilingRefusal(routing={"rows": []}),
            )

    def test_exactly_one_set_is_accepted(self):
        out = ComplaintDraftOut(
            premature_filing_refusal=PrematureFilingRefusal(routing={"rows": []})
        )
        assert out.premature_filing_refusal is not None
        assert out.draft is None
        assert out.illegal_recruitment_refusal is None


class TestFixedRefusalMessages:
    def test_illegal_recruitment_refusal_rejects_a_composed_message(self):
        with pytest.raises(ValidationError):
            IllegalRecruitmentRefusal(
                reason="DIRECT_HIRE",
                agency_status="direct_hire",
                message="something the model made up",
                routing={"rows": []},
            )


class TestNoSubmissionCodePath:
    """Acceptance (PRD #46): fills, never submits — no submission code
    path may exist anywhere under app.complaint."""

    _FORBIDDEN_TOKENS = (
        "requests.post",
        "requests.put",
        "httpx.post",
        "httpx.Client",
        "httpx.AsyncClient",
        "urlopen",
        "submit_sena",
        "submit_complaint",
        "def submit(",
    )

    def _modules(self):
        yield complaint_package
        for info in pkgutil.walk_packages(
            complaint_package.__path__, "app.complaint."
        ):
            yield importlib.import_module(info.name)

    def test_no_network_or_submission_code_exists(self):
        for module in self._modules():
            source = inspect.getsource(module)
            for token in self._FORBIDDEN_TOKENS:
                assert token not in source, (
                    f"{module.__name__} contains {token!r} — no submission "
                    "code path may exist under app.complaint"
                )

    def test_no_module_imports_requests_or_httpx(self):
        for module in self._modules():
            names = set(vars(module))
            assert "requests" not in names
            assert "httpx" not in names
