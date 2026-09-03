"""The claim-template corpus as reviewable data (issue #47).

Acceptance: every entry carries a tier and source; the ADR-0005 register
bounds are structural (a Tier-1 entry resting on a weaker citation, or a
Tier-2 rebuttal that fails to route to the MWO, is unrepresentable).
"""

import pytest
from pydantic import ValidationError

from app.debunker_corpus import CLAIM_TEMPLATES, ClaimTemplate
from app.rules.schema import Citation, SourceTier

STARTING_SET = {
    "placement_fee_debt",
    "cannot_leave_until_repaid",
    "passport_withholding_legal",
    "noc_required_qatar",
    "two_year_lock_in",
}


class TestCorpusShape:
    def test_the_prd_starting_set_is_present(self):
        ids = {t.template_id for t in CLAIM_TEMPLATES}
        assert STARTING_SET <= ids

    def test_template_ids_are_unique(self):
        ids = [t.template_id for t in CLAIM_TEMPLATES]
        assert len(ids) == len(set(ids))

    def test_case_fields_are_unique(self):
        fields = [t.case_field for t in CLAIM_TEMPLATES if t.case_field]
        assert len(fields) == len(set(fields))

    @pytest.mark.parametrize(
        "template", CLAIM_TEMPLATES, ids=lambda t: t.template_id
    )
    def test_every_entry_has_tier_source_and_both_rebuttals(self, template):
        assert template.tier in SourceTier
        assert template.citations, "rebuttal must be cited"
        for citation in template.citations:
            assert citation.source_name
            assert citation.reference
            assert citation.url.startswith("https://")
        assert template.heard_from.source_name, "claim list must be sourced"
        assert template.rebuttal_en.strip()
        assert template.rebuttal_tl.strip()
        assert template.match_stems

    @pytest.mark.parametrize(
        "template",
        [t for t in CLAIM_TEMPLATES if t.tier is SourceTier.TIER_1],
        ids=lambda t: t.template_id,
    )
    def test_tier_1_entries_rest_on_tier_1_primary_citations(self, template):
        assert template.citations[0].tier is SourceTier.TIER_1

    @pytest.mark.parametrize(
        "template",
        [t for t in CLAIM_TEMPLATES if t.tier is SourceTier.TIER_2],
        ids=lambda t: t.template_id,
    )
    def test_tier_2_register_names_its_limit_and_routes_to_the_mwo(
        self, template
    ):
        # ADR-0005: Tier-2 names its source and states its limit.
        assert "MWO" in template.rebuttal_en
        assert "MWO" in template.rebuttal_tl
        assert "reported" in template.rebuttal_en
        assert "ulat" in template.rebuttal_tl

    def test_every_false_verdict_in_the_starting_set_is_plan_relevant(self):
        for template in CLAIM_TEMPLATES:
            if template.template_id in STARTING_SET:
                assert template.verdict == "FALSE"
                assert template.plan_relevant
                assert template.case_field.startswith("debunked_")


class TestTierBoundsAreStructural:
    def _template(self, **overrides) -> ClaimTemplate:
        base = dict(
            template_id="x",
            claim_gloss="x",
            heard_from=CLAIM_TEMPLATES[0].heard_from,
            verdict="FALSE",
            tier=SourceTier.TIER_1,
            citations=(CLAIM_TEMPLATES[0].citations[0],),
            rebuttal_en="No. MWO reported.",
            rebuttal_tl="Hindi. MWO ulat.",
            match_stems=(("stemword",),),
        )
        base.update(overrides)
        return ClaimTemplate(**base)

    def test_tier_1_on_a_tier_2_citation_is_unrepresentable(self):
        tier2 = Citation(
            source_name="a blog",
            reference="says so",
            url="https://example.org",
            tier=SourceTier.TIER_2,
        )
        with pytest.raises(ValidationError, match="never upgrade"):
            self._template(tier=SourceTier.TIER_1, citations=(tier2,))

    def test_tier_2_rebuttal_without_mwo_routing_is_unrepresentable(self):
        with pytest.raises(ValidationError, match="MWO"):
            self._template(
                tier=SourceTier.TIER_2,
                rebuttal_en="Just trust me.",
                rebuttal_tl="Basta.",
            )

    def test_a_rebuttal_without_a_citation_is_unrepresentable(self):
        with pytest.raises(ValidationError, match="citation"):
            self._template(citations=())

    def test_plan_relevant_without_a_case_field_is_unrepresentable(self):
        with pytest.raises(ValidationError, match="case_field"):
            self._template(plan_relevant=True, case_field=None)

    def test_an_unknown_applies_in_jurisdiction_is_unrepresentable(self):
        with pytest.raises(ValidationError, match="unknown jurisdictions"):
            self._template(applies_in=("QA", "XX"))
