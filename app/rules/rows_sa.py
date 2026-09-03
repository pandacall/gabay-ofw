"""Saudi Arabia rule rows (issue #36). Ships at Tier-2 register.

Per issue #36 and ADR-0005, every Saudi row ships at Tier-2 even where an
official Saudi government source exists: a row may downgrade its source's
tier (more restrictive is always safe), never upgrade it. Consequences,
enforced structurally by the schema:

- every filing step is PROTECTIVE_REVERSIBLE;
- no hard-date assertions — the 12-month limitation is a
  ReportedDeadline, reported-not-relied-upon, confirm with the MWO;
- exit-visa (final exit) timing is a confirm-first note, never a
  countdown;
- the 90-day non-withdrawal warning ships unhedged, at full strength.

Sources: Musaned / HRSD official channels (Tier-1 sources cited by Tier-2
rows), the 2023 Regulation for Domestic Workers, Amnesty International
reporting on Filipino and Kenyan domestic workers in Saudi Arabia, and
Saudi labor-court procedural practice as reported by practice guides and
Philippine MWO advisories (warning-only content).
"""

from __future__ import annotations

from app.rules.schema import (
    ActionClass,
    Citation,
    FilingTiming,
    Grievance,
    Jurisdiction,
    ReportedDeadline,
    RuleRow,
    SourceTier,
    TenureBucket,
    Warning,
)

_CIT_MUSANED_FS = Citation(
    source_name=(
        "Musaned — Friendly Settlement service (Saudi Ministry of Human "
        "Resources and Social Development)"
    ),
    reference=(
        "Official HRSD channel for domestic-worker labor disputes: "
        "friendly settlement first, unresolved cases referred onward"
    ),
    url="https://www.musaned.com.sa/en/friendly-settlement",
    tier=SourceTier.TIER_1,
)

_CIT_SA_DW_REG = Citation(
    source_name=(
        "Regulation for Domestic Workers and Those in Similar Positions "
        "(Saudi Council of Ministers, 2023; in force from 2024)"
    ),
    reference=(
        "HRSD-published regulation governing domestic-worker rights and "
        "dispute settlement"
    ),
    url=(
        "https://www.hrsd.gov.sa/sites/default/files/2024-09/"
        "Regulation%20for%20Domestic%20Workers%20and%20Those%20in%20"
        "Similar%20Positions.pdf"
    ),
    tier=SourceTier.TIER_1,
)

_CIT_AMNESTY_PH_2026 = Citation(
    source_name=(
        "Amnesty International, 'Once we step in their homes, we are no "
        "longer human' — testimonies of Filipino women domestic workers "
        "in Saudi Arabia (2026)"
    ),
    reference=(
        "Documents the huroob (absconding) system, counter-accusation "
        "risk, passport confiscation, and barriers to redress for "
        "Filipino domestic workers"
    ),
    url=(
        "https://www.amnesty.org.au/wp-content/uploads/2026/07/"
        "Amnesty-International-Once-we-step-in-their-homes-we-are-no-"
        "longer-human-Testimonies-of-Filipino-women-domestic-workers-in-"
        "Saudi-Arabia.pdf"
    ),
    tier=SourceTier.TIER_2,
)

_CIT_AMNESTY_KE_2025 = Citation(
    source_name=(
        "Amnesty International, 'Locked in, Left Out: The Hidden Lives "
        "of Kenyan Domestic Workers in Saudi Arabia' (2025)"
    ),
    reference=(
        "Documents the huroob system and exclusion of domestic workers "
        "from Labor Law protections in practice"
    ),
    url="https://www.amnesty.org/en/documents/mde23/9222/2025/en/",
    tier=SourceTier.TIER_2,
)

_CIT_SA_ART_222 = Citation(
    source_name=(
        "Saudi Labor Law (Royal Decree No. M/51), Article 222 — as "
        "reported by Saudi legal practice guides"
    ),
    reference=(
        "Twelve-month limitation on labor claims after the end of the "
        "employment relationship, as reported; not independently "
        "verified against the Official Gazette text"
    ),
    url="https://alothmanlaw.sa/en/saudi-labor-office-complaints/",
    tier=SourceTier.TIER_2,
)

_CIT_SA_90_DAY = Citation(
    source_name=(
        "Saudi labor-court procedural practice, as reported by Saudi "
        "legal practice guides and Philippine MWO advisories"
    ),
    reference=(
        "A labor case withdrawn by the worker or struck off for absence "
        "cannot be refiled for 90 days; MWO orientation warns workers "
        "not to withdraw complaints under settlement pressure"
    ),
    url="https://www.ews-limited.com/saudi-labor-court-and-dispute-handling/",
    tier=SourceTier.TIER_2,
)

# Ships unhedged at full strength (ADR-0005: warnings are never softened
# by tier; being wrong about this only makes her more careful).
_W_SA_90_DAY = Warning(
    text=(
        "Do not withdraw your labor complaint, and do not miss a "
        "scheduled hearing. A withdrawn or struck-off case cannot be "
        "refiled for 90 days — long enough for a claim and a residency "
        "to run out together. Pressure to withdraw during settlement "
        "talks is how claims die."
    ),
    citation=_CIT_SA_90_DAY,
)

_W_SA_HUROOB = Warning(
    text=(
        "Once you leave your employer, the employer can file an "
        "absconding (huroob) report against you. That report can lead "
        "to arrest and deportation, and it does not erase your wage "
        "claim. File your complaint immediately and tell the MWO where "
        "you are."
    ),
    citation=_CIT_AMNESTY_PH_2026,
)

_W_SA_NO_POLICE = Warning(
    text=(
        "Do not go to the local police on your own. Filipino domestic "
        "workers who reported abuse to Saudi police have faced "
        "counter-accusations, including theft and 'immoral behaviour' "
        "charges. Go to the MWO first."
    ),
    citation=_CIT_AMNESTY_PH_2026,
)

_SA_MONEY_DEADLINE = ReportedDeadline(
    reported_text=(
        "Saudi Labor Law Article 222 is reported to bar labor claims "
        "filed more than twelve months after the end of the employment "
        "relationship. Treat this as a reason to file early, not as a "
        "clock to run down."
    ),
    confirm_with=(
        "MWO (Migrant Workers Office — country office listed in the "
        "official DMW directory at dmw.gov.ph)"
    ),
)

_SA_FILE_WHERE_IN_COUNTRY = (
    "Musaned platform (musaned.com.sa) Friendly Settlement for domestic "
    "workers, or the Ministry of Human Resources and Social Development "
    "(HRSD) — hotline 19911 / labor office; unresolved cases are "
    "referred onward to the competent labor dispute body. Ask the MWO to "
    "assist with the filing."
)

_SA_FS_PROCESS_NOTE = (
    "The Musaned/HRSD friendly-settlement stage is reported to run for "
    "21 days before referral onward; treat that as process colour, not a "
    "date to rely on."
)

SA_RULE_ROWS: tuple[RuleRow, ...] = (
    # ------------------------------------------------------------------
    # UNPAID_WAGES (wages and end-of-service money claims)
    # ------------------------------------------------------------------
    RuleRow(
        row_id="sa-wages-employed",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.UNPAID_WAGES,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=_SA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=_SA_MONEY_DEADLINE,
        citation=_CIT_MUSANED_FS,
        tier=SourceTier.TIER_2,
        warnings=(_W_SA_90_DAY,),
        notes=(
            "Filing the complaint is protective and reversible: it "
            "creates a record and does not commit you to leaving or to "
            "any confrontation.",
            _SA_FS_PROCESS_NOTE,
        ),
    ),
    RuleRow(
        row_id="sa-wages-left-employer",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.UNPAID_WAGES,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=_SA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=_SA_MONEY_DEADLINE,
        citation=_CIT_MUSANED_FS,
        tier=SourceTier.TIER_2,
        warnings=(_W_SA_HUROOB, _W_SA_90_DAY),
        notes=(
            "Filing before any move to leave the country is the order "
            "that protects the claim: the complaint creates the record "
            "that answers a huroob report.",
            _SA_FS_PROCESS_NOTE,
        ),
    ),
    RuleRow(
        row_id="sa-wages-departed",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.UNPAID_WAGES,
        tenure=TenureBucket.DEPARTED_COUNTRY,
        file_where=(
            "MWO (Migrant Workers Office) and DMW assistance from the "
            "Philippines; a claim in Saudi Arabia is reported to be "
            "pursuable through an authorized representative"
        ),
        filing_timing=FilingTiming.FROM_ABROAD,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=_SA_MONEY_DEADLINE,
        citation=_CIT_AMNESTY_PH_2026,
        tier=SourceTier.TIER_2,
        warnings=(_W_SA_90_DAY,),
        confirm_first_notes=(
            "Whether and how a Saudi labor claim can be filed or "
            "continued from abroad must be confirmed with the MWO before "
            "relying on any channel.",
        ),
    ),
    # ------------------------------------------------------------------
    # PASSPORT_WITHHELD
    # ------------------------------------------------------------------
    RuleRow(
        row_id="sa-passport-employed",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.PASSPORT_WITHHELD,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=_SA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_SA_DW_REG,
        tier=SourceTier.TIER_2,
        notes=(
            "The 2023 Regulation for Domestic Workers prohibits the "
            "employer from keeping the worker's personal documents; "
            "Amnesty documents that confiscation remains widespread in "
            "practice — report it, and tell the MWO.",
        ),
    ),
    RuleRow(
        row_id="sa-passport-left-employer",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.PASSPORT_WITHHELD,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=_SA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_SA_DW_REG,
        tier=SourceTier.TIER_2,
        warnings=(_W_SA_HUROOB,),
        notes=(
            "Do not return to the employer's home to retrieve the "
            "passport; recovery goes through the complaint with MWO "
            "assistance. The embassy can issue a travel document if the "
            "passport cannot be recovered.",
        ),
    ),
    # ------------------------------------------------------------------
    # PHYSICAL_ABUSE_OR_DANGER
    # ------------------------------------------------------------------
    RuleRow(
        row_id="sa-abuse-employed",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.PHYSICAL_ABUSE_OR_DANGER,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=(
            "MWO (Migrant Workers Office — country office listed in the "
            "official DMW directory at dmw.gov.ph) first; then the labor "
            "complaint through Musaned / HRSD hotline 19911 with MWO "
            "assistance"
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_AMNESTY_PH_2026,
        tier=SourceTier.TIER_2,
        warnings=(_W_SA_NO_POLICE,),
        notes=(
            "Capture what evidence you safely can before anything else "
            "changes; the MWO can arrange shelter.",
        ),
    ),
    RuleRow(
        row_id="sa-abuse-left-employer",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.PHYSICAL_ABUSE_OR_DANGER,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=(
            "MWO (Migrant Workers Office — country office listed in the "
            "official DMW directory at dmw.gov.ph) first; then the labor "
            "complaint through Musaned / HRSD hotline 19911 with MWO "
            "assistance"
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_AMNESTY_PH_2026,
        tier=SourceTier.TIER_2,
        warnings=(_W_SA_NO_POLICE, _W_SA_HUROOB),
        notes=(
            "Reaching the MWO shelter and filing the complaint are both "
            "reversible; they protect the abuse record and the wage "
            "claim at once.",
        ),
    ),
    # ------------------------------------------------------------------
    # STATUS_RETALIATION (huroob / absconding report filed against her)
    # ------------------------------------------------------------------
    RuleRow(
        row_id="sa-status-left-employer",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.STATUS_RETALIATION,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=(
            "MWO (Migrant Workers Office) immediately; contesting a "
            "huroob (absconding) report runs through HRSD / Absher "
            "channels with MWO or legal assistance"
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_AMNESTY_PH_2026,
        tier=SourceTier.TIER_2,
        confirm_first_notes=(
            "The window and procedure for contesting an absconding "
            "report are reported to be short and to change; confirm the "
            "current procedure with the MWO before relying on any "
            "timing.",
        ),
        notes=(
            "A pending labor complaint of yours is the strongest answer "
            "to a huroob report — if none is filed yet, file it now.",
        ),
    ),
    # ------------------------------------------------------------------
    # EXIT_BLOCKED (final-exit timing: confirm-first, never a countdown)
    # ------------------------------------------------------------------
    RuleRow(
        row_id="sa-exit-employed",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.EXIT_BLOCKED,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=(
            "Speak to the MWO (Migrant Workers Office) before any "
            "departure step. Final-exit ('final exit' visa) requests run "
            "through Absher / HRSD channels."
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_SA_DW_REG,
        tier=SourceTier.TIER_2,
        confirm_first_notes=(
            "Final-exit procedure and timing must be confirmed with the "
            "MWO before acting: an employer objection window is reported "
            "to exist, and a pending labor case is reported to block "
            "final exit until it is resolved. The order in which you "
            "file and leave decides whether the claim survives — this is "
            "a confirm-first item, never a countdown.",
        ),
    ),
    RuleRow(
        row_id="sa-exit-left-employer",
        jurisdiction=Jurisdiction.SA,
        grievance=Grievance.EXIT_BLOCKED,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=(
            "Speak to the MWO (Migrant Workers Office) before any "
            "departure step. Final-exit ('final exit' visa) requests run "
            "through Absher / HRSD channels."
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_SA_DW_REG,
        tier=SourceTier.TIER_2,
        warnings=(_W_SA_HUROOB,),
        confirm_first_notes=(
            "Final-exit procedure and timing must be confirmed with the "
            "MWO before acting: an employer objection window is reported "
            "to exist, and a pending labor case is reported to block "
            "final exit until it is resolved. Leaving before filing can "
            "extinguish the claim; filing then leaving needs MWO "
            "confirmation of the exit path. Confirm first.",
        ),
    ),
)
