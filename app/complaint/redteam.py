"""``safety_review`` (issue #46, PRD #34): the red-team pass over
COMPLAINT_DRAFTER's own drafted intake narrative.

A fixed, deterministic checklist — no embeddings, the same discipline as
DEBUNKER's ``classify_claim`` (stem groups over normalized text) and
ROUTING_GUARD's token matching. Draft -> red-team -> revise: COMPLAINT_
DRAFTER calls this tool with its own drafted narrative, and if any
finding fires, its instruction is to revise the narrative addressing
every finding's guidance and call again — this module only ever refuses
or clears, so the checklist itself is CI-gate testable independent of
any model turn.

Seven checks, in the fixed order PRD #34 / issue #46 name them:

1. ``ABSCONDING_ADMISSION`` — the draft states she has left, or is
   leaving, her employer without permission. In Saudi Arabia this is
   literally a "huroob" (absconding) report the employer can already
   file; handing the same admission to a document the agency receives
   verbatim helps nobody but the employer.
2. ``VENUE_SCOPE_MISMATCH`` — the draft asks SEnA — a labor money-claims
   and illegal-dismissal conciliation venue — to resolve something it
   cannot hear: a criminal prosecution, an arrest, an exit/immigration
   order.
3. ``PREMATURE_IDENTIFICATION`` — STRUCTURAL, not a text scan: naming her
   in a document a party in contact with her employer will read, before
   she is safely out, while an acute grievance or safety flag is on her
   Case. Fires on the (tenure, grievance, safety_flags) facts themselves,
   regardless of what the narrative says — no rewording clears it; only
   her situation changing does (COMPLAINT_DRAFTER's agent wiring treats
   this one specially: it stops the revise loop and returns the fixed
   :class:`~app.complaint.schema.PrematureFilingRefusal` instead).
4-7. ``AGENCY_LEAK_*`` — in SEnA the recruitment agency is a respondent
   and the party most likely still in contact with the employer (issue
   #46): the draft must never reveal that she is leaving, that she is in
   a shelter, her specific location, or that she has already spoken to
   the MWO. These four are pure text-scan checks: the whole point of
   "draft -> red-team -> revise" is that a narrative that never mentions
   any of them clears cleanly, and one that slips up gets caught and
   rewritten.
"""

from __future__ import annotations

import unicodedata

from app.complaint.schema import RedTeamCheckId, RedTeamFinding, RedTeamResult
from app.rules.schema import Grievance, TenureBucket

#: Grievances whose presence, combined with not-yet-departed tenure,
#: makes premature identification a live risk (PRD #46: "naming her
#: before she is out"). Public: the agent wiring's own
#: ``complaint_check_safe_to_file`` gate uses the same threshold, so the
#: two checks cannot drift apart.
ACUTE_GRIEVANCES = frozenset(
    {Grievance.PHYSICAL_ABUSE_OR_DANGER, Grievance.EXIT_BLOCKED}
)

_GUIDANCE: dict[RedTeamCheckId, str] = {
    RedTeamCheckId.ABSCONDING_ADMISSION: (
        "Remove any statement that she has left, or plans to leave, her "
        "employer without permission — an admission the agency can use "
        "as an absconding/huroob report against her."
    ),
    RedTeamCheckId.VENUE_SCOPE_MISMATCH: (
        "Remove any claim that SEnA will prosecute, arrest, or resolve a "
        "criminal or immigration matter — SEnA hears money claims and "
        "illegal dismissal only; route anything else to the MWO or the "
        "proper authority instead."
    ),
    RedTeamCheckId.PREMATURE_IDENTIFICATION: (
        "She has an acute safety grievance and has not yet left the "
        "country — do not file an identified complaint with a party in "
        "contact with her employer until she is safely out; route to "
        "the Safe Floor / MWO instead of a named filing for now."
    ),
    RedTeamCheckId.AGENCY_LEAK_DEPARTURE_INTENT: (
        "Remove any statement that she is leaving or planning to leave — "
        "the agency is in contact with her employer and must not learn "
        "this from her own filing."
    ),
    RedTeamCheckId.AGENCY_LEAK_SHELTER: (
        "Remove any mention that she is in a shelter or safe house — "
        "this must never reach a party in contact with her employer."
    ),
    RedTeamCheckId.AGENCY_LEAK_LOCATION: (
        "Remove her current address or specific whereabouts — a filing "
        "the agency receives must not disclose where she physically is."
    ),
    RedTeamCheckId.AGENCY_LEAK_MWO_CONTACT: (
        "Remove any statement that she has already contacted the MWO — "
        "this is process detail the agency does not need and should not "
        "learn from her own filing."
    ),
}

# ---------------------------------------------------------------------------
# Deterministic text scanning — same normalize/stem-match technique as
# DEBUNKER's classify_claim (app/debunker.py), duplicated narrowly here
# rather than shared, since the two closed corpora evolve independently.
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    cleaned = "".join(ch if ch.isalnum() else " " for ch in stripped)
    return " ".join(cleaned.split())


def _find_stem(stem: str, norm: str) -> str | None:
    """Returns a short excerpt around ``stem`` in ``norm`` if present."""
    if stem not in norm:
        return None
    idx = norm.index(stem)
    start = max(0, idx - 15)
    end = min(len(norm), idx + len(stem) + 15)
    return norm[start:end].strip()


#: (check_id, stems) — any one stem present fires the check. Bilingual
#: (English / Tagalog) coverage, hand-written, closed set.
_TEXT_CHECKS: tuple[tuple[RedTeamCheckId, tuple[str, ...]], ...] = (
    (
        RedTeamCheckId.ABSCONDING_ADMISSION,
        (
            "tumakas",
            "tumakas ako",
            "umalis ako nang hindi nagsabi",
            "ran away",
            "escaped from my employer",
            "left without telling",
            "left without permission",
            "fled my employer",
            "absent without leave",
            "awol",
        ),
    ),
    (
        RedTeamCheckId.VENUE_SCOPE_MISMATCH,
        (
            "ikukulong",
            "aarestuhin",
            "criminal charges",
            "criminal case",
            "assault charges",
            "file rape",
            "file abuse case",
            "deportation order",
            "exit ban",
        ),
    ),
    (
        RedTeamCheckId.AGENCY_LEAK_DEPARTURE_INTENT,
        (
            "aalis na ako",
            "plano kong umalis",
            "planning to leave",
            "about to leave",
            "i am leaving",
            "i plan to leave",
            "preparing to leave",
        ),
    ),
    (
        RedTeamCheckId.AGENCY_LEAK_SHELTER,
        (
            "shelter",
            "safe house",
            "safehouse",
            "kinukupkop",
        ),
    ),
    (
        RedTeamCheckId.AGENCY_LEAK_LOCATION,
        (
            "current address",
            "kasalukuyang address",
            "present address",
            "staying at",
            "nakatira ako sa",
            "nagtatago ako sa",
            "tumira ako sa",
        ),
    ),
    (
        RedTeamCheckId.AGENCY_LEAK_MWO_CONTACT,
        (
            "sinabihan ko na ang mwo",
            "kausap ko na ang mwo",
            "informed the mwo",
            "already spoke to the mwo",
            "already contacted the mwo",
            "the mwo said",
            "coordinated with the mwo",
        ),
    ),
)


def _text_findings(narrative: str) -> list[RedTeamFinding]:
    norm = _normalize(narrative)
    findings: list[RedTeamFinding] = []
    for check_id, stems in _TEXT_CHECKS:
        for stem in stems:
            excerpt = _find_stem(stem, norm)
            if excerpt is not None:
                findings.append(
                    RedTeamFinding(
                        check_id=check_id,
                        matched_excerpt=excerpt,
                        guidance=_GUIDANCE[check_id],
                    )
                )
                break  # one finding per check per pass is enough to fail it
    return findings


def _structural_findings(
    *,
    tenure: TenureBucket,
    grievances: tuple[Grievance, ...],
    safety_flags: tuple[str, ...],
) -> list[RedTeamFinding]:
    findings: list[RedTeamFinding] = []
    acute = bool(safety_flags) or any(g in ACUTE_GRIEVANCES for g in grievances)
    if acute and tenure is not TenureBucket.DEPARTED_COUNTRY:
        findings.append(
            RedTeamFinding(
                check_id=RedTeamCheckId.PREMATURE_IDENTIFICATION,
                matched_excerpt=None,
                guidance=_GUIDANCE[RedTeamCheckId.PREMATURE_IDENTIFICATION],
            )
        )
    return findings


def safety_review(
    narrative: str,
    *,
    tenure: TenureBucket,
    grievances: tuple[Grievance, ...],
    safety_flags: tuple[str, ...] = (),
) -> RedTeamResult:
    """Runs the fixed leak-check list against one drafted narrative.

    Pure function: no model, no I/O. Text-scan findings (absconding
    admissions, venue-scope mismatches, and the four agency-leak checks)
    come from ``narrative`` itself; ``PREMATURE_IDENTIFICATION`` also
    fires structurally from the true facts (her tenure, grievances, and
    safety flags) regardless of what the text says — no rewording clears
    it, by design (see module docstring).
    """
    findings = _text_findings(narrative)
    seen = {finding.check_id for finding in findings}
    for finding in _structural_findings(
        tenure=tenure,
        grievances=grievances,
        safety_flags=safety_flags,
    ):
        if finding.check_id not in seen:
            findings.append(finding)
            seen.add(finding.check_id)
    if not findings:
        return RedTeamResult(cleared=True, findings=(), revision_count=0)
    return RedTeamResult(cleared=False, findings=tuple(findings))
