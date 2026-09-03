"""``render_pdf`` smoke tests (issue #46): form-fill from a Case + Plan
fixture through to a rendered PDF."""

from __future__ import annotations

import base64

from app.complaint.pdf import render_pdf_base64, render_sena_rfa_pdf
from app.complaint.schema import (
    AgencyInfo,
    EmployerInfo,
    WorkerInfo,
)
from app.complaint.sena_form import fill_sena_rfa
from app.rules.schema import Grievance


def _fixture_fields():
    return fill_sena_rfa(
        worker=WorkerInfo(full_name="Maria Santos", sex="female"),
        employer=EmployerInfo(name="Al Rashid Household", address="Riyadh"),
        agency=AgencyInfo(name="Sample Overseas Manpower Services, Inc."),
        grievances=(Grievance.UNPAID_WAGES,),
        has_wage_loss=True,
    )


class TestPdfRendering:
    def test_renders_a_pdf_document(self):
        pdf_bytes = render_sena_rfa_pdf(_fixture_fields())
        assert pdf_bytes.startswith(b"%PDF")
        assert pdf_bytes.rstrip().endswith(b"%%EOF")

    def test_base64_round_trips_to_the_same_bytes(self):
        fields = _fixture_fields()
        raw = render_sena_rfa_pdf(fields)
        encoded = render_pdf_base64(fields)
        assert base64.b64decode(encoded) == raw

    def test_handles_non_latin1_citation_text_without_raising(self):
        # The SEnA citation source_name contains an em dash; must not
        # crash the core-font renderer.
        pdf_bytes = render_sena_rfa_pdf(_fixture_fields())
        assert len(pdf_bytes) > 0
