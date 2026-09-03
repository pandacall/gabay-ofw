"""COMPLAINT_DRAFTER (issue #46, PRD #34): fills, never submits.

The typed boundary lives in :mod:`app.complaint.schema`; the pure
correctness dependencies in :mod:`app.complaint.agency` (``check_agency_
license``), :mod:`app.complaint.redteam` (``safety_review``),
:mod:`app.complaint.loss_calc` (the Arabic arithmetic-only wage loss
calculation), and :mod:`app.complaint.sena_form` (the SEnA RFA field
fill); PDF rendering in :mod:`app.complaint.pdf`; the single-turn agent in
:mod:`app.complaint.agent`.
"""

from app.complaint.agent import COMPLAINT_DRAFTER_NAME, build_complaint_drafter
from app.complaint.schema import ComplaintDraftIn, ComplaintDraftOut, FormDraft

__all__ = [
    "COMPLAINT_DRAFTER_NAME",
    "ComplaintDraftIn",
    "ComplaintDraftOut",
    "FormDraft",
    "build_complaint_drafter",
]
