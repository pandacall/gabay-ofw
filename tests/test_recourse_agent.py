"""RECOURSE_ROUTER agent-wiring tests (issue #48): tool-wrapper unit test
plus the HTTP-seam demoable path (PRD #34's testing decision: "same
grievance, two agency-license states, visibly different door lists").

The pure route-table fixtures (license fork, repatriation track,
regional-office fork, AKSYON Fund tiers) live in
``tests/test_recourse_routes.py`` and are exercised directly against
``build_recourse_routes`` — no model. This file only covers the parts a
pure-function suite cannot: the tool wrapper's ``ToolContext`` surface,
the guard/voice-whitelist integration, and one full DISPATCHER turn at
the NDJSON seam using the house's fake-injection ``FakeModelRunner``
pattern (mirrors ``tests/test_complaint_drafter_agent.py`` /
``tests/test_proof_builder_api.py``).
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field

from app.agent import GEMINI_MODEL
from app.chat import ChatService
from app.guard import ALLOWED_TOOLS, guard_before_tool
from app.main import create_app
from app.recourse.agent import (
    RECOURSE_ROUTER_NAME,
    build_recourse_router,
    recourse_build_routes,
)
from app.recourse.routes import build_recourse_routes
from app.recourse.schema import RecourseRouteIn, RecourseRouterOut


class _FakeState(dict):
    pass


class _FakeToolContext:
    """Minimal stand-in exposing only ``.state`` — the only ToolContext
    surface ``recourse_build_routes`` touches (it currently touches
    none, but the wrapper still takes one, matching every other
    specialist's tool signature)."""

    def __init__(self):
        self.state = _FakeState()


LICENSED_ROUTE_IN = {
    "country": "SA",
    "tenure": "employed_in_country",
    "grievances": ["unpaid_wages"],
    "agency": {"name": "Sample Overseas Manpower Services, Inc."},
    "family_region": None,
}

UNLICENSED_ROUTE_IN = {
    **LICENSED_ROUTE_IN,
    "agency": {"name": "Placeholder Global Recruitment Corp."},
}


class TestRecourseBuildRoutesTool:
    """No model, no HTTP: the tool wrapper directly."""

    def test_licensed_agency_returns_sena_and_solidary_routes(self):
        ctx = _FakeToolContext()
        result = recourse_build_routes(
            RecourseRouteIn(**LICENSED_ROUTE_IN), ctx
        )
        venues = [r["venue"] for r in result["routes"]]
        assert any("Single Entry Approach" in v for v in venues)
        assert any("jointly and severally liable" in v for v in venues)

    def test_unlicensed_agency_returns_illegal_recruitment_only(self):
        ctx = _FakeToolContext()
        result = recourse_build_routes(
            RecourseRouteIn(**UNLICENSED_ROUTE_IN), ctx
        )
        venues = [r["venue"] for r in result["routes"]]
        assert any("anti-illegal-recruitment" in v for v in venues)
        assert not any("Single Entry Approach" in v for v in venues)

    def test_result_shape_matches_output_schema(self):
        ctx = _FakeToolContext()
        result = recourse_build_routes(
            RecourseRouteIn(**LICENSED_ROUTE_IN), ctx
        )
        # Round-trips through the output_schema unchanged.
        RecourseRouterOut.model_validate(result)


class TestRoutingGuardIntegration:
    def test_recourse_router_and_its_tool_are_allowlisted(self):
        assert "RECOURSE_ROUTER" in ALLOWED_TOOLS
        assert "recourse_build_routes" in ALLOWED_TOOLS

    def test_agent_carries_the_second_guard_rail_and_disallows_transfer(self):
        class _Model(BaseLlm):
            model: str = GEMINI_MODEL

            async def generate_content_async(self, llm_request, stream=False):
                yield LlmResponse(
                    content=types.Content(role="model", parts=[types.Part(text="{}")])
                )

        agent = build_recourse_router(_Model())
        assert agent.before_tool_callback is guard_before_tool
        assert agent.disallow_transfer_to_parent
        assert agent.disallow_transfer_to_peers
        assert agent.input_schema is RecourseRouteIn
        assert agent.output_schema is RecourseRouterOut


# ---------------------------------------------------------------------------
# HTTP-seam: same grievance, two agency-license states, visibly different
# door lists (PRD #34's demoable acceptance criterion for issue #48).
# ---------------------------------------------------------------------------

EXTRACTION = json.dumps(
    {
        "language": "en",
        "claims": {"country": {"value": "Saudi Arabia", "confidence": "high"}},
        "safety_flags": [],
    }
)


class FakeModelRunnerWithRecourseRouter(BaseLlm):
    """Serves extraction, DISPATCHER, and RECOURSE_ROUTER turns.

    Distinguishes RECOURSE_ROUTER's own node the same way
    ``FakeModelRunnerWithComplaintDrafter`` does: by the exact tool set
    visible to that turn (``{"recourse_build_routes"}``) rather than by
    ``response_schema`` — a single-turn agent that has BOTH tools and an
    ``output_schema`` still calls tools first; only the FINAL (no more
    scripted tool calls) turn's text is validated against
    ``RecourseRouterOut``.
    """

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    dispatcher_router_args: list = Field(default_factory=list)
    dispatcher_replies: list = Field(default_factory=list)
    router_calls: list = Field(default_factory=list)
    router_final: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)
    requests: list = Field(default_factory=list)

    _ROUTER_TOOL_NAMES = {"recourse_build_routes"}

    async def generate_content_async(self, llm_request, stream: bool = False):
        tool_names = set(llm_request.tools_dict or {})
        self.requests.append((tool_names, llm_request))
        schema = llm_request.config.response_schema if llm_request.config else None

        if tool_names and tool_names >= self._ROUTER_TOOL_NAMES:
            if self.router_calls:
                self.calls.append("recourse_router_tool_call")
                name, args = self.router_calls.pop(0)
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(name=name, args=args)
                            )
                        ],
                    )
                )
                return
            self.calls.append("recourse_router_final")
            text = self.router_final.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=text)])
            )
            return

        if schema is not None:
            self.calls.append("extraction")
            result = self.extraction_results.pop(0)
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=result)])
            )
            return

        if self.dispatcher_router_args:
            self.calls.append("dispatcher_calls_recourse_router")
            args = self.dispatcher_router_args.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=RECOURSE_ROUTER_NAME, args=args
                            )
                        )
                    ],
                )
            )
            return
        self.calls.append("dispatcher")
        text = self.dispatcher_replies.pop(0) if self.dispatcher_replies else "OK"
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


def auth(uid: str) -> dict:
    scheme = "Be" + "arer"
    return {"Authorization": f"{scheme} valid-{uid}"}


@pytest.fixture()
def fake_model():
    return FakeModelRunnerWithRecourseRouter()


@pytest.fixture()
def client(fake_model):
    service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
    app = create_app(verifier=FakeVerifier(), chat_service=service)
    return TestClient(app)


def turn(client, text, *, uid="maria"):
    response = client.post("/api/chat", json={"text": text}, headers=auth(uid))
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    return {line["type"]: line for line in lines}


def _run_one_turn(client, fake_model, *, route_in: dict, final_routes: dict):
    fake_model.extraction_results.append(EXTRACTION)
    fake_model.dispatcher_router_args.append(route_in)
    fake_model.router_calls.append(("recourse_build_routes", {"route_in": route_in}))
    fake_model.router_final.append(json.dumps(final_routes))
    fake_model.dispatcher_replies.append(
        "Narito ang mga recourse na open sa iyo."
    )
    return turn(client, "Saan ako pwede pumunta para sa reklamo ko?")


class TestDemoableDoorListsDifferAtTheHttpSeam:
    """Acceptance: same grievance, two agency-license states, visibly
    different door lists — asserted at the NDJSON seam, not just the
    pure function."""

    def test_licensed_agency_streams_sena_and_solidary_routes(
        self, client, fake_model
    ):
        route_in = RecourseRouteIn(**LICENSED_ROUTE_IN)
        routes = [
            r.model_dump(mode="json") for r in build_recourse_routes(route_in)
        ]
        by_type = _run_one_turn(
            client,
            fake_model,
            route_in=LICENSED_ROUTE_IN,
            final_routes={"routes": routes},
        )

        streamed = by_type["recourse_routes"]["recourse_routes"]["routes"]
        venues = [r["venue"] for r in streamed]
        assert any("Single Entry Approach" in v for v in venues)
        assert any("jointly and severally liable" in v for v in venues)
        assert fake_model.calls == [
            "extraction",
            "dispatcher_calls_recourse_router",
            "recourse_router_tool_call",
            "recourse_router_final",
            "dispatcher",
        ]

    def test_unlicensed_agency_streams_a_visibly_different_door_list(
        self, client, fake_model
    ):
        route_in = RecourseRouteIn(**UNLICENSED_ROUTE_IN)
        routes = [
            r.model_dump(mode="json") for r in build_recourse_routes(route_in)
        ]
        by_type = _run_one_turn(
            client,
            fake_model,
            route_in=UNLICENSED_ROUTE_IN,
            final_routes={"routes": routes},
        )

        streamed = by_type["recourse_routes"]["recourse_routes"]["routes"]
        venues = [r["venue"] for r in streamed]
        assert any("anti-illegal-recruitment" in v for v in venues)
        assert not any("Single Entry Approach" in v for v in venues)
        assert not any("jointly and severally liable" in v for v in venues)

    def test_recourse_router_saw_only_the_typed_route_in_no_conversation(
        self, client, fake_model
    ):
        route_in = RecourseRouteIn(**LICENSED_ROUTE_IN)
        routes = [
            r.model_dump(mode="json") for r in build_recourse_routes(route_in)
        ]
        by_type = _run_one_turn(
            client,
            fake_model,
            route_in=LICENSED_ROUTE_IN,
            final_routes={"routes": routes},
        )
        assert "recourse_routes" in by_type

        texts = []
        for tool_names, request in fake_model.requests:
            if not (tool_names and tool_names >= {"recourse_build_routes"}):
                continue
            for content in request.contents or []:
                for part in content.parts or []:
                    if part.text:
                        texts.append(part.text)
        assert texts, "RECOURSE_ROUTER never ran"
        assert all(
            "Saan ako pwede pumunta" not in text for text in texts
        )

    def test_recourse_routes_stream_on_the_ndjson_seam_not_only_in_prose(
        self, client, fake_model
    ):
        route_in = RecourseRouteIn(**LICENSED_ROUTE_IN)
        routes = [
            r.model_dump(mode="json") for r in build_recourse_routes(route_in)
        ]
        by_type = _run_one_turn(
            client,
            fake_model,
            route_in=LICENSED_ROUTE_IN,
            final_routes={"routes": routes},
        )
        # Same seam as COMPLAINT_DRAFTER's own result (ADR-0002): the UI
        # renders the typed payload; the voice only frames it.
        assert by_type["reply"]["text"] == "Narito ang mga recourse na open sa iyo."
        assert by_type["recourse_routes"]["recourse_routes"]["routes"]
