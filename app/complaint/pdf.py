"""``render_pdf`` (issue #46, PRD #34): renders a filled SEnA RFA to PDF
bytes. Fills, never submits — this module performs no network I/O and
exposes no submission path; it only ever turns :class:`SenaRfaFields`
into a byte string the caller may hand back to her.
"""

from __future__ import annotations

import base64

from fpdf import FPDF

from app.complaint.schema import SenaRfaFields

_NATURE_LABELS = {
    "money_claims": "Money Claims (unpaid wages / benefits)",
    "illegal_dismissal": "Illegal Dismissal",
}
_RELIEF_LABELS = {
    "payment_of_claims": "Payment of Claims",
    "other": "Other",
}
_ROLE_LABELS = {
    "employer": "Employer",
    "recruitment_agency": "Recruitment Agency",
}

#: Common punctuation the core Helvetica font (latin-1 only) can't
#: encode, transliterated to a plain-ASCII equivalent before anything
#: reaches fpdf. Anything else unencodable falls back to "?" rather than
#: raising — a rendering nicety must never block handing her the PDF.
_PUNCT_MAP = {
    "\u2014": "-",
    "\u2013": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
}


def _safe(text: str) -> str:
    for needle, replacement in _PUNCT_MAP.items():
        text = text.replace(needle, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _multi_cell(pdf: FPDF, height: float, text: str) -> None:
    """``multi_cell`` with the cursor explicitly reset to the left
    margin afterwards. fpdf2's own default for ``new_x`` is
    ``XPos.RIGHT`` — leaving the cursor at the right edge of a
    width-``0`` cell, which starves the NEXT ``multi_cell(0, ...)`` call
    of horizontal space and raises ``FPDFException``. Every text line in
    this module goes through this helper so that gotcha can't recur."""
    pdf.multi_cell(0, height, text, new_x="LMARGIN", new_y="NEXT")


def render_sena_rfa_pdf(fields: SenaRfaFields) -> bytes:
    """Renders ``fields`` to a single-page PDF. Pure formatting — every
    value it prints already crossed schema validation upstream."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    _multi_cell(pdf, 8, _safe(fields.form_title))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    _multi_cell(pdf, 7, "Requesting Party")
    pdf.set_font("Helvetica", "", 10)
    _multi_cell(pdf, 6, _safe(f"Name: {fields.requesting_party_name}"))
    if fields.requesting_party_sex:
        _multi_cell(
            pdf, 6, _safe(f"Sex: {fields.requesting_party_sex.value.title()}")
        )
    if fields.requesting_party_address:
        _multi_cell(pdf, 6, _safe(f"Address: {fields.requesting_party_address}"))
    if fields.requesting_party_contact:
        _multi_cell(pdf, 6, _safe(f"Contact: {fields.requesting_party_contact}"))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    _multi_cell(pdf, 7, "Responding Party / Parties")
    pdf.set_font("Helvetica", "", 10)
    for party in fields.responding_parties:
        role = _ROLE_LABELS.get(party.role.value, party.role.value)
        line = f"{role}: {party.name}"
        if party.address:
            line += f" ({party.address})"
        _multi_cell(pdf, 6, _safe(line))
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    _multi_cell(pdf, 7, "Nature of Request")
    pdf.set_font("Helvetica", "", 10)
    for nature in fields.nature_of_request:
        _multi_cell(
            pdf, 6, _safe(f"[x] {_NATURE_LABELS.get(nature.value, nature.value)}")
        )
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    _multi_cell(pdf, 7, "Relief Sought")
    pdf.set_font("Helvetica", "", 10)
    for relief in fields.relief_sought:
        _multi_cell(
            pdf, 6, _safe(f"[x] {_RELIEF_LABELS.get(relief.value, relief.value)}")
        )
    pdf.ln(2)

    if fields.supporting_documents:
        pdf.set_font("Helvetica", "B", 11)
        _multi_cell(pdf, 7, "Supporting Documents")
        pdf.set_font("Helvetica", "", 10)
        for doc in fields.supporting_documents:
            _multi_cell(pdf, 6, _safe(f"- {doc}"))
        pdf.ln(2)

    pdf.set_font("Helvetica", "I", 9)
    _multi_cell(pdf, 6, _safe(fields.filing_note))
    pdf.ln(1)
    _multi_cell(pdf, 6, _safe(f"Source: {fields.source.source_name}"))

    output = pdf.output()
    return bytes(output)


def render_pdf_base64(fields: SenaRfaFields) -> str:
    """``render_sena_rfa_pdf`` result, base64-encoded for the JSON tool
    boundary (ADK tool results must be JSON-serializable)."""
    return base64.b64encode(render_sena_rfa_pdf(fields)).decode("ascii")
