"""RECOURSE_ROUTER as an agent: wiring the pure route table into
DISPATCHER (issue #48, PRD #34).

RECOURSE_ROUTER is a ``mode='single_turn'`` :class:`LlmAgent` attached to
DISPATCHER via ``sub_agents=[...]`` — the same integration pattern as
FILING_SEQUENCER (issue #42), DEBUNKER (issue #47), PROOF_BUILDER (issue
#45), and COMPLAINT_DRAFTER (issue #46): typed ``input_schema``/
``output_schema``, its own ``before_tool_callback=guard_before_tool`` (the
second, independent ROUTING_GUARD rail), and transfers disallowed both
ways. Unlike COMPLAINT_DRAFTER's ordered gate-then-fill pipeline,
RECOURSE_ROUTER's whole job is one deterministic lookup — a single tool
call that returns every open door for the situation it was given, never a
refusal (an unlicensed agency or an already-out worker is itself a valid
route, not a dead end).
"""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.tools import ToolContext

from app.guard import guard_before_tool
from app.recourse.routes import build_recourse_routes
from app.recourse.schema import RecourseRouteIn, RecourseRouterOut

RECOURSE_ROUTER_NAME = "RECOURSE_ROUTER"


def recourse_build_routes(
    route_in: RecourseRouteIn, tool_context: ToolContext
) -> dict[str, Any]:
    """Every open door for one worker situation: the license fork (SEnA
    plus the RA 8042/10022 solidary lever, or illegal recruitment), the
    already-out-of-the-house fork (OWWA repatriation, no filing route),
    and the additive AKSYON Fund route — see
    :func:`app.recourse.routes.build_recourse_routes` for the full
    derivation. Pure and deterministic: given the same typed input, the
    same routes come back every time."""
    routes = build_recourse_routes(route_in)
    return {"routes": [route.model_dump(mode="json") for route in routes]}


_INSTRUCTION = """\
You are RECOURSE_ROUTER. You never talk to the worker directly — your
input is typed arguments only: her country, tenure situation, the
grievances she reported, her recruitment agency (or direct-hire flag),
and her family's location in the Philippines if known. You never see
this conversation.

Call recourse_build_routes(route_in) exactly once with those arguments,
unchanged. Respond with exactly {"routes": <the returned routes list,
unchanged>} — never add, drop, reorder, or reword a route, never invent
a venue, an executor, a prerequisite, or a source the tool did not
return, and never call the tool a second time to try for a different
result.
"""


def build_recourse_router(llm: BaseLlm) -> LlmAgent:
    """Builds RECOURSE_ROUTER: ``mode='single_turn'``, closed-enum
    ``input_schema``, its one pure-function-backed tool, and a structured
    ``output_schema``. Attach via ``sub_agents=[...]`` on DISPATCHER —
    google-adk auto-wraps this as ONE tool named ``RECOURSE_ROUTER``.
    """
    return LlmAgent(
        name=RECOURSE_ROUTER_NAME,
        mode="single_turn",
        model=llm,
        # Isolation is structural, not an accident of defaults — the same
        # discipline as every other specialist: this agent never sees
        # conversation history, only the typed RecourseRouteIn.
        include_contents="none",
        description=(
            "Determines which legal recourses are open for her case and "
            "who can execute each: the agency-license fork (SEnA plus the "
            "solidary-liability lever, or illegal recruitment), the "
            "already-out-of-the-house fork (OWWA repatriation, not "
            "filing), and the AKSYON Fund support route. Never a refusal "
            "— every fork returns a real door."
        ),
        instruction=_INSTRUCTION,
        input_schema=RecourseRouteIn,
        output_schema=RecourseRouterOut,
        tools=[recourse_build_routes],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        before_tool_callback=guard_before_tool,
    )
