"""The DEBUNKER claim-template corpus (issue #47, PRD #34).

A closed set of hand-sourced claim templates — the lies (and one true
warning) a Filipino domestic worker in the Gulf is actually told, each
with a cited rebuttal. ``search_corpus`` classifies over this set
deterministically: no embeddings, which removes the vector-poisoning
surface entirely and makes refusal fixture-testable.

Two research tasks feed each entry (PRD #34 Further Notes), kept separate
in the data:

- ``heard_from`` sources the CLAIM — evidence that workers are actually
  told this (Amnesty testimony reports, ILO guides addressing the myth).
- ``citations`` source the REBUTTAL — what makes the verdict true, with a
  Source Tier per ADR-0005.

Tier sets the register (ADR-0005): a Tier-1 rebuttal asserts flatly; a
Tier-2 rebuttal names its source and states its limit ("not confirmed
against the statute text; the MWO can confirm"). The register lives in
the rebuttal text itself so rendering is deterministic; validators below
make a Tier-1 entry resting on a sub-Tier-1 citation, or a Tier-2 entry
whose rebuttal fails to route to the MWO, unrepresentable.

Template order is classification precedence: the first matching template
wins, so the most movement-restricting belief ("you can't leave") is
listed before the belief it usually rides on (the placement-fee debt).

See docs/debunker-corpus.md for the sourcing derivation table.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from app.rules.schema import Citation, SourceTier

# ---------------------------------------------------------------------------
# Citations — rebuttal sources first, then claim-list sources.
# ---------------------------------------------------------------------------

_CIT_POEA_2016_RULE_V = Citation(
    source_name=(
        "2016 Revised POEA Rules and Regulations Governing the Recruitment "
        "and Employment of Landbased Overseas Filipino Workers (administered "
        "by the DMW)"
    ),
    reference=(
        "Rule V, Section 51 — no placement fee may be charged against "
        "household service workers (domestic workers); the no-placement-fee "
        "policy for HSWs dates from POEA Governing Board Resolution No. 06, "
        "s. 2006"
    ),
    url=(
        "https://dmw.gov.ph/archives/laws&rules/files/"
        "2016%20Revised%20POEA%20RULES%20And%20REGULATIONS.pdf"
    ),
    tier=SourceTier.TIER_1,
)

# Mirrors the verified citations in app/rules/rows_qa.py (issue #36).
_CIT_ILO_KYR_QA = Citation(
    source_name=(
        "ILO, 'Know Your Rights — Qatar Labour Law' (ILO Project Office "
        "for the State of Qatar)"
    ),
    reference=(
        "Job change procedure under Decree-Law No. 18 of 2020: an employer "
        "No Objection Certificate (NOC) is no longer required to change "
        "jobs in Qatar"
    ),
    url=(
        "https://www.mrrors.org/wp-content/uploads/2023/09/"
        "Know-Your-Rights_Qatar-as-of-Sep-17.pdf"
    ),
    tier=SourceTier.TIER_1,
)

_CIT_ILO_KYR_DW_QA = Citation(
    source_name=(
        "ILO, 'Know Your Rights: A booklet for domestic workers in Qatar'"
    ),
    reference=(
        "Law No. 21 of 2015 Section 8(3): the employer must return the "
        "worker's passport; withholding it is a punishable offence. Law "
        "No. 15 of 2017 Sections 12 and 17: the contract can be ended "
        "early, without notice where the employer has violated it"
    ),
    url=(
        "https://www.ilo.org/publications/"
        "know-your-rights-booklet-domestic-workers-qatar"
    ),
    tier=SourceTier.TIER_1,
)

# Mirrors the verified citation in app/rules/rows_sa.py (issue #36).
_CIT_SA_DW_REG_2023 = Citation(
    source_name=(
        "Regulation for Domestic Workers and Those in Similar Positions "
        "(Saudi Council of Ministers, 2023; in force from 2024)"
    ),
    reference=(
        "HRSD-published regulation governing domestic-worker rights, "
        "including the prohibition on the employer retaining the worker's "
        "passport and personal documents"
    ),
    url=(
        "https://www.hrsd.gov.sa/sites/default/files/2024-09/"
        "Regulation%20for%20Domestic%20Workers%20and%20Those%20in%20"
        "Similar%20Positions.pdf"
    ),
    tier=SourceTier.TIER_1,
)

# Copied verbatim from app/rules/rows_sa.py (_CIT_SA_90_DAY).
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

# Claim-list source: documents the beliefs planted on Filipino domestic
# workers in Saudi Arabia (recruitment-debt claims, passport confiscation
# framed as normal, being told they cannot leave).
_HEARD_AMNESTY_PH_2026 = Citation(
    source_name=(
        "Amnesty International, 'Once we step in their homes, we are no "
        "longer human' — testimonies of Filipino women domestic workers "
        "in Saudi Arabia (2026)"
    ),
    reference=(
        "Testimonies document workers being told they owe recruitment/"
        "placement debts, that they cannot leave until the debt is repaid "
        "or the contract completed, and passport confiscation presented "
        "as the employer's right"
    ),
    url=(
        "https://www.amnesty.org.au/wp-content/uploads/2026/07/"
        "Amnesty-International-Once-we-step-in-their-homes-we-are-no-"
        "longer-human-Testimonies-of-Filipino-women-domestic-workers-in-"
        "Saudi-Arabia.pdf"
    ),
    tier=SourceTier.TIER_2,
)

_HEARD_ILO_NOC_MYTH = Citation(
    source_name=(
        "ILO, 'Know Your Rights — Qatar Labour Law' (ILO Project Office "
        "for the State of Qatar)"
    ),
    reference=(
        "The guide answers the NOC question directly because workers in "
        "Qatar are still routinely told an employer NOC is required to "
        "change jobs after Decree-Law No. 18 of 2020 abolished it"
    ),
    url=(
        "https://www.mrrors.org/wp-content/uploads/2023/09/"
        "Know-Your-Rights_Qatar-as-of-Sep-17.pdf"
    ),
    tier=SourceTier.TIER_1,
)

_HEARD_MWO_ORIENTATION = Citation(
    source_name="Philippine MWO orientation advisories (Saudi Arabia)",
    reference=(
        "MWO orientation warns workers about the 90-day non-withdrawal "
        "rule because employers use settlement pressure to get complaints "
        "withdrawn"
    ),
    url="https://dmw.gov.ph",
    tier=SourceTier.TIER_2,
)


# ---------------------------------------------------------------------------
# Template schema
# ---------------------------------------------------------------------------

VerdictLiteral = Literal["FALSE", "TRUE"]


class ClaimTemplate(BaseModel):
    """One hand-sourced claim template with its cited, tiered rebuttal.

    ``match_stems`` is a tuple of stem groups: a claim matches when every
    stem in any single group is found in the normalized claim text (see
    ``app.debunker`` for the deterministic matching rules).
    """

    model_config = ConfigDict(frozen=True)

    template_id: str
    #: The claim as she is told it — canonical phrasing for reviewers.
    claim_gloss: str
    #: Evidence workers are actually told this (claim-list research task).
    heard_from: Citation
    verdict: VerdictLiteral
    #: The register the rebuttal ships at (ADR-0005). May be a deliberate
    #: downgrade of a stronger citation, never an upgrade of a weaker one.
    tier: SourceTier
    #: Rebuttal sources (rebuttal research task); the first is primary.
    citations: tuple[Citation, ...]
    rebuttal_en: str
    rebuttal_tl: str
    match_stems: tuple[tuple[str, ...], ...]
    #: Jurisdictions (Country codes) where this entry's verdict holds.
    #: None means everywhere the app serves. A matched claim outside the
    #: set is NOT asserted — it fails closed to NOT_COVERED and routes to
    #: the MWO (the NOC entry is false IN QATAR, not everywhere).
    applies_in: Optional[tuple[str, ...]] = None
    #: A FALSE verdict on a plan-relevant belief writes to the Case so a
    #: Plan resting on it goes stale via the input-hash mechanism (#43).
    plan_relevant: bool = False
    case_field: Optional[str] = None

    @model_validator(mode="after")
    def _enforce_bounds(self) -> "ClaimTemplate":
        if not self.citations:
            raise ValueError(
                f"template {self.template_id!r}: a rebuttal without a "
                "citation is not a rebuttal"
            )
        if not self.match_stems:
            raise ValueError(
                f"template {self.template_id!r}: no match stems — the "
                "template would be unreachable"
            )
        if (
            self.tier is SourceTier.TIER_1
            and self.citations[0].tier is not SourceTier.TIER_1
        ):
            raise ValueError(
                f"template {self.template_id!r}: a Tier-1 rebuttal must "
                "rest on a Tier-1 primary citation — an entry may "
                "downgrade its source's tier, never upgrade it (ADR-0005)"
            )
        if self.tier is SourceTier.TIER_2:
            for label, text in (
                ("rebuttal_en", self.rebuttal_en),
                ("rebuttal_tl", self.rebuttal_tl),
            ):
                if "MWO" not in text:
                    raise ValueError(
                        f"template {self.template_id!r}: a Tier-2 "
                        f"{label} must state its limit and route to the "
                        "MWO (ADR-0005 register)"
                    )
        if self.plan_relevant and not self.case_field:
            raise ValueError(
                f"template {self.template_id!r}: plan_relevant requires "
                "a case_field for the Case write"
            )
        if self.applies_in is not None:
            unknown = set(self.applies_in) - {"SA", "QA", "KW", "AE"}
            if unknown:
                raise ValueError(
                    f"template {self.template_id!r}: applies_in contains "
                    f"unknown jurisdictions {sorted(unknown)}"
                )
        return self


# ---------------------------------------------------------------------------
# The corpus. Order is classification precedence.
# ---------------------------------------------------------------------------

CLAIM_TEMPLATES: tuple[ClaimTemplate, ...] = (
    ClaimTemplate(
        template_id="cannot_leave_until_repaid",
        claim_gloss=(
            "'You can't leave / go home until you repay what you owe' — "
            "continued work demanded against a claimed recruitment debt."
        ),
        heard_from=_HEARD_AMNESTY_PH_2026,
        verdict="FALSE",
        tier=SourceTier.TIER_1,
        citations=(_CIT_POEA_2016_RULE_V,),
        rebuttal_en=(
            "No. The 'debt' this rests on does not exist: DMW (POEA) "
            "rules — 2016 Revised POEA Rules, Rule V, Section 51 — forbid "
            "charging a domestic worker any placement fee, so there is "
            "nothing to repay. Nobody may lawfully keep you working to "
            "pay off a claimed recruitment debt. Before you actually "
            "leave, talk to the MWO so leaving does not hurt a wage "
            "claim — but the debt is not a reason you must stay."
        ),
        rebuttal_tl=(
            "Hindi totoo. Ang 'utang' na pinagbabatayan nito ay hindi "
            "umiiral: bawal sa patakaran ng DMW (POEA) — 2016 Revised "
            "POEA Rules, Rule V, Section 51 — ang maningil ng placement "
            "fee sa domestic worker, kaya walang dapat bayaran. Walang "
            "sinumang may karapatang pilitin kang magtrabaho para "
            "bayaran ang di-umano'y utang sa recruitment. Bago ka "
            "talagang umalis, kausapin muna ang MWO para hindi masira "
            "ang habol mo sa sahod — pero ang utang ay hindi dahilan "
            "para manatili ka."
        ),
        match_stems=(
            ("leave", "repay"),
            ("leave", "utang"),
            ("leave", "debt"),
            ("leave", "bayar"),
            ("alis", "utang"),
            ("alis", "bayar"),
            ("umuwi", "utang"),
            ("umuwi", "bayar"),
            ("uuwi", "utang"),
            ("uuwi", "bayar"),
            ("go home", "utang"),
            ("go home", "debt"),
            ("go home", "repay"),
            ("go home", "pay"),
        ),
        plan_relevant=True,
        case_field="debunked_cannot_leave_until_repaid",
    ),
    ClaimTemplate(
        template_id="placement_fee_debt",
        claim_gloss=(
            "'Utang mo ang placement fee' — she owes the agency or "
            "employer a placement fee and must pay it off."
        ),
        heard_from=_HEARD_AMNESTY_PH_2026,
        verdict="FALSE",
        tier=SourceTier.TIER_1,
        citations=(_CIT_POEA_2016_RULE_V,),
        rebuttal_en=(
            "You owe no placement fee. Under the DMW (POEA) rules — 2016 "
            "Revised POEA Rules, Rule V, Section 51 — no placement fee "
            "may be charged to a domestic worker. An agency or employer "
            "claiming this debt is claiming money the rules forbid it to "
            "collect; charging it is illegal recruitment you can report "
            "to the DMW."
        ),
        rebuttal_tl=(
            "Wala kang utang na placement fee. Sa ilalim ng patakaran ng "
            "DMW (POEA) — 2016 Revised POEA Rules, Rule V, Section 51 — "
            "bawal singilin ng placement fee ang domestic worker. Kung "
            "sinisingil ka ng agency o amo, paniningil iyon na bawal sa "
            "patakaran; illegal recruitment iyon at maaari mo itong "
            "i-report sa DMW."
        ),
        match_stems=(
            ("placement", "utang"),
            ("placement", "owe"),
            ("placement", "debt"),
            ("placement", "bayar"),
            ("placement", "kaltas"),
            ("placement", "deduct"),
            ("placement", "balance"),
            ("agency", "utang"),
            ("agency", "owe"),
            ("agency", "debt"),
        ),
        plan_relevant=True,
        case_field="debunked_placement_fee_debt",
    ),
    ClaimTemplate(
        template_id="passport_withholding_legal",
        claim_gloss=(
            "'It's legal for the employer to keep your passport' — "
            "confiscation presented as the employer's right."
        ),
        heard_from=_HEARD_AMNESTY_PH_2026,
        verdict="FALSE",
        tier=SourceTier.TIER_1,
        citations=(_CIT_ILO_KYR_DW_QA, _CIT_SA_DW_REG_2023),
        rebuttal_en=(
            "No — keeping your passport is not your employer's right. In "
            "Qatar, Law No. 21 of 2015, Section 8(3) requires the "
            "employer to return your passport, and keeping it is a "
            "punishable offence. In Saudi Arabia, the Regulation for "
            "Domestic Workers (2023) likewise prohibits the employer "
            "from retaining your passport and personal documents. Report "
            "withholding with the MWO's help."
        ),
        rebuttal_tl=(
            "Hindi — walang karapatan ang amo mo na hawakan ang passport "
            "mo. Sa Qatar, ayon sa Law No. 21 of 2015, Section 8(3), "
            "dapat ibalik ng amo ang passport mo, at may parusa ang "
            "pagtatago nito. Sa Saudi Arabia, ipinagbabawal din ng "
            "Regulation for Domestic Workers (2023) na hawakan ng amo "
            "ang passport at mga personal na dokumento mo. I-report ang "
            "paghawak nito sa tulong ng MWO."
        ),
        match_stems=(
            ("passport", "legal"),
            ("passport", "allowed"),
            ("passport", "right"),
            ("passport", "pwede"),
            ("passport", "karapatan"),
            ("passport", "batas"),
            ("pasaporte", "legal"),
            ("pasaporte", "pwede"),
            ("pasaporte", "karapatan"),
            ("pasaporte", "batas"),
        ),
        plan_relevant=True,
        case_field="debunked_passport_withholding_legal",
    ),
    ClaimTemplate(
        template_id="noc_required_qatar",
        claim_gloss=(
            "'You need an NOC (No Objection Certificate) from your "
            "employer to change jobs' — false in Qatar since 2020."
        ),
        heard_from=_HEARD_ILO_NOC_MYTH,
        verdict="FALSE",
        tier=SourceTier.TIER_1,
        citations=(_CIT_ILO_KYR_QA,),
        rebuttal_en=(
            "False in Qatar. Since Decree-Law No. 18 of 2020 you can "
            "change employers by following the Ministry of Labour "
            "procedure — a No Objection Certificate (NOC) from your "
            "employer is not required. The ILO 'Know Your Rights — Qatar "
            "Labour Law' guide describes the current job-change "
            "procedure."
        ),
        rebuttal_tl=(
            "Hindi totoo sa Qatar. Mula sa Decree-Law No. 18 of 2020, "
            "maaari kang lumipat ng employer sa pamamagitan ng proseso "
            "ng Ministry of Labour — hindi kailangan ng No Objection "
            "Certificate (NOC) mula sa amo mo. Nakasaad ang kasalukuyang "
            "proseso ng paglipat ng trabaho sa ILO na 'Know Your Rights "
            "— Qatar Labour Law'."
        ),
        match_stems=(
            ("noc",),
            ("no objection",),
        ),
        # False IN QATAR (Decree-Law 18/2020). Elsewhere the corpus does
        # not cover the claim: a match outside QA fails closed to
        # NOT_COVERED and routes to the MWO instead of asserting.
        applies_in=("QA",),
        plan_relevant=True,
        case_field="debunked_noc_required_qatar",
    ),
    ClaimTemplate(
        template_id="two_year_lock_in",
        claim_gloss=(
            "'You must complete two years before you can leave / go "
            "home / complain' — the contract term framed as compulsory "
            "servitude."
        ),
        heard_from=_HEARD_AMNESTY_PH_2026,
        verdict="FALSE",
        # Deliberate downgrade: the primary citation is Tier-1 for Qatar,
        # but the rebuttal generalizes to Saudi Arabia on MWO-advisory
        # reporting, so the entry ships at Tier-2 (ADR-0005: an entry may
        # downgrade its source's tier, never upgrade it).
        tier=SourceTier.TIER_2,
        citations=(_CIT_ILO_KYR_DW_QA,),
        rebuttal_en=(
            "The contract term is not a prison sentence. For Qatar, the "
            "ILO 'Know Your Rights' booklet for domestic workers states "
            "the contract can be ended early — including without notice "
            "where the employer has violated it. For Saudi Arabia the "
            "same is reported by Philippine MWO advisories but is not "
            "confirmed here against the statute text — the MWO can "
            "confirm what applies to your contract, and what leaving "
            "early would cost you, before you act."
        ),
        rebuttal_tl=(
            "Ang termino ng kontrata ay hindi kulungan. Sa Qatar, ayon "
            "sa ILO 'Know Your Rights' booklet para sa mga domestic "
            "worker, maaaring tapusin nang maaga ang kontrata — kabilang "
            "ang pag-alis nang walang abiso kung nilabag ito ng amo. Sa "
            "Saudi Arabia, ganito rin ang ulat ng mga abiso ng "
            "Philippine MWO pero hindi pa ito nakumpirma dito laban sa "
            "mismong teksto ng batas — makukumpirma ng MWO kung ano ang "
            "tumutukoy sa kontrata mo, at ang magiging kapalit ng "
            "maagang pag-alis, bago ka kumilos."
        ),
        match_stems=(
            ("two year",),
            ("2 year",),
            ("dalawang taon",),
            ("complete", "contract"),
            ("finish", "contract"),
            ("tapusin", "kontrata"),
        ),
        plan_relevant=True,
        case_field="debunked_two_year_lock_in",
    ),
    ClaimTemplate(
        template_id="sa_ninety_day_withdrawal",
        claim_gloss=(
            "'If you withdraw your labor complaint (or miss a hearing) "
            "you cannot refile for 90 days' — true as reported, and it "
            "matters."
        ),
        heard_from=_HEARD_MWO_ORIENTATION,
        verdict="TRUE",
        tier=SourceTier.TIER_2,
        citations=(_CIT_SA_90_DAY,),
        rebuttal_en=(
            "That one is true, as reported by Saudi legal practice "
            "guides and Philippine MWO advisories: a labor case you "
            "withdraw — or that is struck off because you missed a "
            "hearing — cannot be refiled for 90 days. It is not "
            "confirmed here against the statute text; the MWO can "
            "confirm. Do not withdraw your complaint under settlement "
            "pressure, and do not miss hearings."
        ),
        rebuttal_tl=(
            "Totoo iyan, ayon sa ulat ng mga Saudi legal practice guide "
            "at ng mga abiso ng Philippine MWO: ang kasong in-withdraw "
            "mo — o na-dismiss dahil lumiban ka sa hearing — ay hindi "
            "maaaring i-refile sa loob ng 90 araw. Hindi pa ito "
            "nakumpirma dito laban sa mismong teksto ng batas; "
            "makukumpirma ito ng MWO. Huwag i-withdraw ang reklamo mo "
            "dahil sa pressure na makipag-ayos, at huwag lumiban sa "
            "hearing."
        ),
        match_stems=(
            ("90", "withdraw"),
            ("90", "refile"),
            ("90", "complaint"),
            ("90", "reklamo"),
            ("90", "kaso"),
            ("ninety", "withdraw"),
        ),
        plan_relevant=False,
    ),
)
