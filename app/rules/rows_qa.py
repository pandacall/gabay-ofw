"""Qatar rule rows (issue #36). Ships at full strength: Tier-1 base.

Primary sources (ADR-0005 Tier-1):

- Qatar Labour Law No. 14 of 2004 (as amended) — Al Meezan, the official
  Qatar legal portal.
- Law No. 13 of 2017 (Art. 115 bis: Labour Dispute Settlement Committees).
- ILO, "Know Your Rights — Qatar Labour Law" and ILO, "Know Your Rights:
  A booklet for domestic workers in Qatar" — ILO material published under
  the ILO–Qatar technical cooperation programme, which ADR-0005 counts as
  Tier-1. Row content was verified against the booklet texts directly.
"""

from __future__ import annotations

from app.rules.schema import (
    ActionClass,
    Citation,
    FilingTiming,
    Grievance,
    HardDeadline,
    Jurisdiction,
    RuleRow,
    SourceTier,
    TenureBucket,
    Warning,
)

_CIT_QA_ART_10 = Citation(
    source_name="Qatar Labour Law No. 14 of 2004 (as amended)",
    reference=(
        "Article 10 — no claim arising from the Law is heard after one "
        "year from the date the cause of action arose"
    ),
    url="https://www.almeezan.qa/LawPage.aspx?id=3961&language=en",
    tier=SourceTier.TIER_1,
)

_CIT_QA_LAW_13_2017 = Citation(
    source_name="Qatar Law No. 13 of 2017 amending the Labour Law",
    reference=(
        "Article 115 bis — complaint to the Ministry of Labour, amicable "
        "settlement within 7 days, referral to the Labour Dispute "
        "Settlement Committee, committee decision within 3 weeks of the "
        "first hearing"
    ),
    url="https://www.almeezan.qa/LawView.aspx?LawID=7310",
    tier=SourceTier.TIER_1,
)

_CIT_ILO_KYR = Citation(
    source_name=(
        "ILO, 'Know Your Rights — Qatar Labour Law' (ILO Project Office "
        "for the State of Qatar)"
    ),
    reference=(
        "Complaints via the Ministry of Labour helpline 16008 / 16505, "
        "the Unified Platform for Complaints and Whistleblowers at "
        "mol.gov.qa; job change and QID-cancellation procedure under "
        "Decree-Law No. 18 of 2020"
    ),
    url=(
        "https://www.mrrors.org/wp-content/uploads/2023/09/"
        "Know-Your-Rights_Qatar-as-of-Sep-17.pdf"
    ),
    tier=SourceTier.TIER_1,
)

_CIT_ILO_KYR_DW = Citation(
    source_name=(
        "ILO, 'Know Your Rights: A booklet for domestic workers in Qatar'"
    ),
    reference=(
        "Law No. 15 of 2017 (Domestic Workers Law) Sections 7, 12, 15, "
        "17; Law No. 21 of 2015 Section 8(3); Ministry of Interior "
        "Decision No. 95 of 2019 Article 2"
    ),
    url=(
        "https://www.ilo.org/publications/"
        "know-your-rights-booklet-domestic-workers-qatar"
    ),
    tier=SourceTier.TIER_1,
)

_QA_MONEY_DEADLINE = HardDeadline(
    duration_days=365,
    starts_from=(
        "the date the cause of action arose (the unpaid wage fell due, or "
        "the employment relationship ended)"
    ),
)

_QA_FILE_WHERE_IN_COUNTRY = (
    "Ministry of Labour (MoL): Unified Platform for Complaints and "
    "Whistleblowers at mol.gov.qa, hotline 16008, or the Labour Relations "
    "Department in person (take all employment documents)"
)

_QA_PROCESS_NOTE = (
    "Official process: the MoL attempts amicable settlement within 7 days "
    "of the complaint; unresolved disputes are referred to the Labour "
    "Dispute Settlement Committee, which must decide within 3 weeks of "
    "its first hearing (Law No. 13 of 2017, Art. 115 bis)."
)

_W_QA_NOTICE_REENTRY_BAN = Warning(
    text=(
        "If you leave Qatar without completing your notice period, you "
        "will not be able to return to work in Qatar for one year from "
        "the date you leave."
    ),
    citation=_CIT_ILO_KYR,
)

QA_RULE_ROWS: tuple[RuleRow, ...] = (
    # ------------------------------------------------------------------
    # UNPAID_WAGES (wages and end-of-service money claims)
    # ------------------------------------------------------------------
    RuleRow(
        row_id="qa-wages-employed",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.UNPAID_WAGES,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=_QA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=_QA_MONEY_DEADLINE,
        citation=_CIT_QA_ART_10,
        tier=SourceTier.TIER_1,
        notes=(
            _QA_PROCESS_NOTE,
            "Wages must be paid through the Wage Protection System within "
            "7 days of the due date (Labour Law Arts. 65-66 as amended by "
            "Law No. 17 of 2020); a missed WPS deposit is itself "
            "complaint-ready evidence.",
            "End-of-service benefit: at least three weeks' basic wage per "
            "year of service after one full year (Labour Law Art. 54; "
            "Domestic Workers Law No. 15 of 2017 Sec. 15). Same venue, "
            "same deadline.",
        ),
    ),
    RuleRow(
        row_id="qa-wages-left-employer",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.UNPAID_WAGES,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=_QA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=_QA_MONEY_DEADLINE,
        citation=_CIT_QA_ART_10,
        tier=SourceTier.TIER_1,
        notes=(
            _QA_PROCESS_NOTE,
            "Leaving the employer does not extinguish the money claim: "
            "the one-year Art. 10 clock is what matters. File before "
            "leaving the country.",
            "If the employer has not fulfilled legal or contractual "
            "obligations, including payment of wages, you can change jobs "
            "without notice — submit the complaint to the MoL Unified "
            "Platform first (Decree-Law No. 18 of 2020).",
        ),
    ),
    RuleRow(
        row_id="qa-wages-departed",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.UNPAID_WAGES,
        tenure=TenureBucket.DEPARTED_COUNTRY,
        file_where=(
            "Ministry of Labour (MoL) Unified Platform for Complaints and "
            "Whistleblowers at mol.gov.qa (online), or through a "
            "representative in Qatar holding a power of attorney"
        ),
        filing_timing=FilingTiming.FROM_ABROAD,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=_QA_MONEY_DEADLINE,
        citation=_CIT_QA_ART_10,
        tier=SourceTier.TIER_1,
        notes=(
            "The Art. 10 one-year limitation keeps running after "
            "departure — file promptly.",
            _QA_PROCESS_NOTE,
        ),
    ),
    # ------------------------------------------------------------------
    # PASSPORT_WITHHELD
    # ------------------------------------------------------------------
    RuleRow(
        row_id="qa-passport-employed",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.PASSPORT_WITHHELD,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=_QA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_ILO_KYR_DW,
        tier=SourceTier.TIER_1,
        notes=(
            "You have the right to keep your passport and travel "
            "documents (Law No. 21 of 2015, Sec. 8(3)); the employer may "
            "hold them only with your written permission.",
            "An employer who withholds a worker's travel documents by "
            "force is violating the law and is subject to a fine of up to "
            "QAR 25,000.",
        ),
    ),
    RuleRow(
        row_id="qa-passport-left-employer",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.PASSPORT_WITHHELD,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=_QA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_ILO_KYR_DW,
        tier=SourceTier.TIER_1,
        notes=(
            "Recovering the passport goes through the MoL complaint, not "
            "through returning to the employer's home. The employer must "
            "return the passport after residence-permit procedures unless "
            "you asked in writing that they keep it (Law No. 21 of 2015, "
            "Sec. 8(3)).",
        ),
    ),
    # ------------------------------------------------------------------
    # PHYSICAL_ABUSE_OR_DANGER
    # ------------------------------------------------------------------
    RuleRow(
        row_id="qa-abuse-employed",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.PHYSICAL_ABUSE_OR_DANGER,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=_QA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_ILO_KYR_DW,
        tier=SourceTier.TIER_1,
        notes=(
            "If the employer or a family member hurts you physically, or "
            "there is serious danger to your life or health, you may end "
            "the contract immediately without notice and keep your full "
            "end-of-service benefit (Domestic Workers Law No. 15 of 2017, "
            "Sec. 17; Labour Law Art. 51). Process the termination "
            "through the Ministry's electronic notification system.",
            "Money claims arising from the same employment keep the "
            "one-year Art. 10 limitation — file them with the same MoL "
            "complaint.",
        ),
    ),
    RuleRow(
        row_id="qa-abuse-left-employer",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.PHYSICAL_ABUSE_OR_DANGER,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=_QA_FILE_WHERE_IN_COUNTRY,
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_ILO_KYR_DW,
        tier=SourceTier.TIER_1,
        notes=(
            "Leaving because of abuse is a lawful no-notice termination "
            "that preserves your end-of-service benefit (Domestic Workers "
            "Law No. 15 of 2017, Sec. 17) — record the reason in the MoL "
            "complaint before leaving the country.",
        ),
    ),
    # ------------------------------------------------------------------
    # STATUS_RETALIATION (QID cancelled before a job change)
    # ------------------------------------------------------------------
    RuleRow(
        row_id="qa-status-employed",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.STATUS_RETALIATION,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=(
            "Ministry of Labour (MoL): Unified Platform for Complaints "
            "and Whistleblowers at mol.gov.qa, or in person; then a "
            "signed letter in Arabic addressed to the Head of the Labour "
            "Relations Department requesting reactivation of your QID"
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_ILO_KYR,
        tier=SourceTier.TIER_1,
        notes=(
            "If your employer cancels your Qatar ID before you submit a "
            "job-change application, file the complaint first; the "
            "Ministry reviews it before the QID reactivation letter "
            "(Decree-Law No. 18 of 2020).",
            "Workers can change jobs within 90 days following QID expiry "
            "when the expiry was for reasons beyond the worker's control.",
        ),
    ),
    RuleRow(
        row_id="qa-status-left-employer",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.STATUS_RETALIATION,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=(
            "Ministry of Labour (MoL): Unified Platform for Complaints "
            "and Whistleblowers at mol.gov.qa, or in person; then a "
            "signed letter in Arabic addressed to the Head of the Labour "
            "Relations Department requesting reactivation of your QID"
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_ILO_KYR,
        tier=SourceTier.TIER_1,
        notes=(
            "A cancelled QID does not cancel your money claims: the "
            "one-year Art. 10 limitation governs those, and the MoL "
            "complaint covers both.",
            "Workers can change jobs within 90 days following QID expiry "
            "when the expiry was for reasons beyond the worker's control.",
        ),
    ),
    # ------------------------------------------------------------------
    # EXIT_BLOCKED
    # ------------------------------------------------------------------
    RuleRow(
        row_id="qa-exit-employed",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.EXIT_BLOCKED,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        file_where=(
            "No exit permit is required to leave Qatar. If departure is "
            "obstructed, complain to the Ministry of Labour: hotline "
            "16008 or the Unified Platform for Complaints and "
            "Whistleblowers at mol.gov.qa"
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_ILO_KYR_DW,
        tier=SourceTier.TIER_1,
        warnings=(_W_QA_NOTICE_REENTRY_BAN,),
        notes=(
            "Domestic workers have the right to leave Qatar temporarily "
            "or definitively during the contract; inform the employer at "
            "least 72 hours in advance, verbally or in writing (Ministry "
            "of Interior Decision No. 95 of 2019, Art. 2).",
            "File any money claim before departure where possible — the "
            "claim survives departure, but filing is simplest in-country.",
        ),
    ),
    RuleRow(
        row_id="qa-exit-left-employer",
        jurisdiction=Jurisdiction.QA,
        grievance=Grievance.EXIT_BLOCKED,
        tenure=TenureBucket.LEFT_EMPLOYER_IN_COUNTRY,
        file_where=(
            "No exit permit is required to leave Qatar. If departure is "
            "obstructed, complain to the Ministry of Labour: hotline "
            "16008 or the Unified Platform for Complaints and "
            "Whistleblowers at mol.gov.qa"
        ),
        filing_timing=FilingTiming.BEFORE_LEAVING_COUNTRY,
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        deadline=None,
        citation=_CIT_ILO_KYR_DW,
        tier=SourceTier.TIER_1,
        warnings=(_W_QA_NOTICE_REENTRY_BAN,),
        notes=(
            "Notice to terminate and leave the country goes through the "
            "Ministry's electronic system; the notice period does not "
            "exceed 2 months (Decree-Law No. 18 of 2020). Leaving for "
            "Sec. 17 reasons (abuse, danger, employer breach) requires no "
            "notice.",
            "File any money claim before departure: the one-year Art. 10 "
            "limitation keeps running either way.",
        ),
    ),
)
