"""PROOF_BUILDER: the single-turn evidence-acquisition specialist (issue #45).

Attached to DISPATCHER via ``sub_agents=[...]`` with
``mode='single_turn'`` — under google-adk 2.8.0 the framework wraps it as
an inline tool automatically (never ``AgentTool``). It declares
``input_schema=BundleState`` so DISPATCHER's function-calling sees typed
parameters (a bare ``request: string`` is banned) and
``output_schema=ProofGap`` so its answer is validated before crossing
back.

The specialist sees NONE of the conversation: single-turn sub-agents run
with ``include_contents='none'`` (isolation scope), so this instruction
assumes no history — its whole world is the BundleState JSON it is
handed. The checklist text below is RENDERED FROM the reviewed data in
:mod:`app.proof.checklists`, so the prompt can never drift from the rows.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm

from app.guard import guard_before_tool
from app.proof.checklists import checklist_for
from app.proof.schema import BundleState, ProofGap, Venue

PROOF_BUILDER_NAME = "PROOF_BUILDER"


def _render_checklists() -> str:
    lines: list[str] = []
    for venue in Venue:
        lines.append(f"Venue {venue.value}:")
        for row in checklist_for(venue):
            subs = (
                " | substitutes, best first: "
                + ", ".join(s.value for s in row.substitutes)
                if row.substitutes
                else ""
            )
            lines.append(
                f"- {row.artifact.value} [{row.requirement.value}] "
                f"({row.purpose}; source: {row.source.source_name}){subs}"
            )
    return "\n".join(lines)


_INSTRUCTION = f"""\
You are PROOF_BUILDER for Gabay OFW. Your input is one JSON object — a
BundleState: the intake venue, the artifacts a Filipino overseas worker
already holds (with condition and structured document facts), the
artifacts she has said she CANNOT get, and her phone risk. You see no
conversation and need none. Reply with ONE ProofGap JSON object and
nothing else.

The venue checklists, from published intake requirements (source per
row; "required" rows are what the office asks for, "strengthens" rows
help the request but are not demanded):

{_render_checklists()}

How to do the gap analysis:

1. SATISFIED: a checklist row is covered only by a held artifact in a
   usable condition. A bad phone photo is not automatically usable:
   judge what it actually is from its facts. An illegible photo, or an
   Arabic-only document where nothing needed is visible, covers
   nothing. But a bad photo of an iqama whose facts show the worker's
   name and an official stamp IS a residence-ID copy — do not make her
   recapture what already serves.
2. OUTSTANDING: every checklist row not covered, with its level.
3. UNOBTAINABLE artifacts (she said she cannot get them): NEVER ask for
   these again. Substitute an obtainable artifact from the row's
   substitute list when one exists. When nothing substitutes, record an
   unclosed gap whose bundle_limit states plainly what the bundle will
   and will not support without it — the plan proceeds around the gap,
   never as if the fact were proven.
4. NEXT_ASK: exactly ONE artifact, or none. Rank candidates by marginal
   value (required before strengthens; a row that closes the biggest
   hole first), obtainability (what she can actually produce from where
   she is), and risk of being caught looking (phone_risk: when the
   phone is watched or she has minutes only, prefer captures that look
   innocent and take seconds — a photo of a receipt over hunting for a
   contract). Say concretely how to capture it given her situation.
5. SUFFICIENT: when every required row is covered (by the artifact or a
   substitute), set sufficient true and make no ask — the loop ends.

scope_limit must be exactly: "This is what the office will ask you for.
It is not a promise about the outcome of your case." You state what the
office asks for; you never predict outcomes, never say anything will
win, and never rank evidence by what persuades a tribunal.
"""


def build_proof_builder(llm: BaseLlm) -> LlmAgent:
    """The PROOF_BUILDER LlmAgent, ready to attach as a sub-agent.

    Attached via ``sub_agents=[...]`` on DISPATCHER; ADK 2.8.0 wraps it
    as a tool named PROOF_BUILDER with the BundleState schema as
    parameters. Transfers are disallowed both ways: specialists never
    chat and never call one another (they couple only through the Case).
    Its tool calls cross ROUTING_GUARD on both rails: the App plugin,
    plus this agent's own before-tool callback (the same second rail
    DISPATCHER carries).
    """
    return LlmAgent(
        name=PROOF_BUILDER_NAME,
        mode="single_turn",
        model=llm,
        # Isolation is structural, not an accident of defaults: this
        # specialist never sees conversation history.
        include_contents="none",
        description=(
            "Evidence gap analysis for one intake venue: compares the "
            "bundle to the venue's published checklist, substitutes "
            "obtainable artifacts, and returns at most ONE next-artifact "
            "ask — or termination on sufficiency."
        ),
        instruction=_INSTRUCTION,
        input_schema=BundleState,
        output_schema=ProofGap,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        before_tool_callback=guard_before_tool,
    )
