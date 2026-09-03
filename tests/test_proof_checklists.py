"""Review suite for the per-venue intake checklists (issue #45).

The checklists are reviewable DATA: every row carries the published
source it was taken from and its ADR-0005 tier. What must NOT appear:
a row without a source, a Tier-1 row resting on a weaker citation, or
tribunal-persuasion framing anywhere in the copy.
"""

import pytest
from pydantic import ValidationError

from app.proof.agent import _INSTRUCTION, build_proof_builder
from app.proof.checklists import (
    INTAKE_CHECKLISTS,
    checklist_for,
    obtainable_substitutes,
    required_artifacts,
)
from app.proof.schema import (
    ArtifactType,
    ChecklistRow,
    RequirementLevel,
    Venue,
)
from app.rules.schema import Citation, SourceTier

# Tribunal persuasion is out of scope; the copy never promises outcomes.
PERSUASION_WORDS = ("win", "convince", "persuade", "guarantee")


class TestReviewableData:
    def test_every_venue_has_rows(self):
        for venue in Venue:
            assert checklist_for(venue), venue

    def test_every_row_has_a_published_source(self):
        for row in INTAKE_CHECKLISTS:
            assert row.source.source_name.strip(), row.row_id
            assert row.source.reference.strip(), row.row_id
            assert row.source.url.startswith("http"), row.row_id

    def test_every_row_records_a_tier(self):
        for row in INTAKE_CHECKLISTS:
            assert row.tier in (SourceTier.TIER_1, SourceTier.TIER_2), row.row_id

    def test_row_ids_unique(self):
        ids = [row.row_id for row in INTAKE_CHECKLISTS]
        assert len(ids) == len(set(ids))

    def test_required_vs_strengthens_recorded_per_artifact(self):
        for venue in Venue:
            levels = {row.requirement for row in checklist_for(venue)}
            assert RequirementLevel.REQUIRED in levels, venue
            assert RequirementLevel.STRENGTHENS in levels, venue

    def test_no_persuasion_framing_anywhere(self):
        for row in INTAKE_CHECKLISTS:
            copy = row.purpose.lower()
            for word in PERSUASION_WORDS:
                assert word not in copy, (row.row_id, word)


class TestSubstitutes:
    def test_a_substitute_is_never_the_artifact_itself(self):
        for row in INTAKE_CHECKLISTS:
            assert row.artifact not in row.substitutes, row.row_id

    def test_the_payslip_nobody_issues_has_a_remittance_substitute(self):
        # The canonical case from issue #45: a remittance receipt for a
        # payslip a Gulf household employer never issues.
        for venue in (Venue.SENA_RFA, Venue.MWO_ATN_INTAKE):
            assert ArtifactType.REMITTANCE_RECEIPT in obtainable_substitutes(
                venue, ArtifactType.PAYSLIP
            ), venue

    def test_the_missing_contract_has_obtainable_substitutes(self):
        # "OFWs don't have their contracts" must become a plan, not a
        # dead end: every venue that lists the contract offers substitutes.
        for venue in Venue:
            rows = [
                r
                for r in checklist_for(venue)
                if r.artifact is ArtifactType.EMPLOYMENT_CONTRACT
            ]
            for row in rows:
                assert row.substitutes, row.row_id


class TestTierBounds:
    def test_tier_never_upgrades_the_source(self):
        for row in INTAKE_CHECKLISTS:
            if row.tier is SourceTier.TIER_1:
                assert row.source.tier is SourceTier.TIER_1, row.row_id

    def test_an_upgraded_row_is_unrepresentable(self):
        tier2_source = Citation(
            source_name="an NGO guide",
            reference="reported requirements",
            url="https://example.org/guide",
            tier=SourceTier.TIER_2,
        )
        with pytest.raises(ValidationError, match="never"):
            ChecklistRow(
                row_id="bad-upgrade",
                venue=Venue.SENA_RFA,
                artifact=ArtifactType.PAYSLIP,
                requirement=RequirementLevel.STRENGTHENS,
                purpose="x",
                source=tier2_source,
                tier=SourceTier.TIER_1,
            )


class TestHelpers:
    def test_required_artifacts_match_the_rows(self):
        assert ArtifactType.PASSPORT_COPY in required_artifacts(
            Venue.MWO_ATN_INTAKE
        )
        assert ArtifactType.VALID_PH_ID in required_artifacts(Venue.SENA_RFA)

    def test_unknown_artifact_has_no_substitutes(self):
        assert (
            obtainable_substitutes(
                Venue.SENA_RFA, ArtifactType.SPECIAL_POWER_OF_ATTORNEY
            )
            == ()
        )


class TestInstructionRendersTheData:
    """The prompt is generated from the rows — it can never drift."""

    def test_every_row_appears_in_the_instruction(self):
        for row in INTAKE_CHECKLISTS:
            assert row.artifact.value in _INSTRUCTION
            assert row.source.source_name in _INSTRUCTION

    def test_the_scope_limit_is_in_the_instruction_verbatim(self):
        from app.proof.schema import SCOPE_LIMIT_LINE

        # The instruction quotes the line (wrapped); compare word stream.
        assert " ".join(SCOPE_LIMIT_LINE.split()) in " ".join(
            _INSTRUCTION.split()
        )

    def test_the_agent_is_single_turn_with_typed_schemas(self):
        from google.adk.models import BaseLlm

        class _Stub(BaseLlm):
            model: str = "stub"

            async def generate_content_async(self, llm_request, stream=False):
                raise AssertionError("never called")
                yield

        agent = build_proof_builder(_Stub())
        assert agent.mode == "single_turn"
        assert agent.include_contents == "none"
        from app.proof.schema import BundleState, ProofGap

        assert agent.input_schema is BundleState
        assert agent.output_schema is ProofGap
