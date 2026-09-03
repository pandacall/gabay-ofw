"""PROOF_BUILDER (issue #45): intake checklists and the evidence loop.

The typed boundary lives in :mod:`app.proof.schema`, the reviewable
per-venue checklist data in :mod:`app.proof.checklists`, and the
single-turn agent in :mod:`app.proof.agent`.
"""

from app.proof.agent import build_proof_builder
from app.proof.checklists import (
    INTAKE_CHECKLISTS,
    checklist_for,
    obtainable_substitutes,
    required_artifacts,
)
from app.proof.schema import (
    SCOPE_LIMIT_LINE,
    ArtifactAsk,
    ArtifactCondition,
    ArtifactType,
    BundleState,
    ChecklistRow,
    Currency,
    DocFacts,
    HeldArtifact,
    OutstandingRow,
    PhoneRisk,
    ProofGap,
    RequirementLevel,
    UnclosedGap,
    Venue,
)

__all__ = [
    "ArtifactAsk",
    "ArtifactCondition",
    "ArtifactType",
    "BundleState",
    "ChecklistRow",
    "Currency",
    "DocFacts",
    "HeldArtifact",
    "INTAKE_CHECKLISTS",
    "OutstandingRow",
    "PhoneRisk",
    "ProofGap",
    "RequirementLevel",
    "SCOPE_LIMIT_LINE",
    "UnclosedGap",
    "Venue",
    "build_proof_builder",
    "checklist_for",
    "obtainable_substitutes",
    "required_artifacts",
]
