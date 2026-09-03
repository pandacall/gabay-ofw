"""DEBUNKER behavioral tests at the HTTP seam (issue #47, PRD #34).

Same pattern as tests/test_chat_api.py: fake verifier, in-memory session
service, and a fake model at the BaseLlm boundary — no internals mocked.
The fake model scripts the turn choreography (DISPATCHER calls the
DEBUNKER tool; DEBUNKER calls search_corpus and echoes its result); the
classification, rebuttals, routing, and the Case write are the real
deterministic code under test.

What must NOT happen, asserted here: NOT_COVERED never renders a bare
refusal (it routes to the MWO with directory-resolved numbers), and no
number in the routing payload is model-generated.
"""

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
from app.debunker_corpus import CLAIM_TEMPLATES
from app.directory import Channel, Country, office_directory_rows
from app.main import create_app

DISPATCHER_REPLY = "Hindi totoo ang sinabi nila sa iyo."

TAGLISH_EXTRACTION = json.dumps(
    {
        "language": "taglish",
        "claims": {"country": {"value": "Saudi Arabia", "confidence": "high"}},
        "safety_flags": [],
    }
)


def _tool_names(llm_request) -> set[str]:
    names = set()
    config = llm_request.config
    for tool in (config.tools if config and config.tools else []) or []:
        for decl in getattr(tool, "function_declarations", None) or []:
            names.add(decl.name)
    return names


def _last_function_response(llm_request):
    contents = llm_request.contents or []
    if not contents:
        return None
    for part in contents[-1].parts or []:
        if part.function_response is not None:
            return part.function_response
    return None


class DebunkingFakeModel(BaseLlm):
    """Scripts the DISPATCHER -> DEBUNKER -> search_corpus choreography.

    ``claimset`` is what DISPATCHER passes to the DEBUNKER tool. The
    DEBUNKER final output echoes the real search_corpus result into the
    typed Verdicts shape, exactly as the instruction demands.
    """

    model: str = GEMINI_MODEL
    extraction_results: list = Field(default_factory=list)
    claimset: dict = Field(default_factory=dict)

    async def generate_content_async(self, llm_request, stream: bool = False):
        config = llm_request.config
        if config and config.response_schema is not None:
            text = self.extraction_results.pop(0)
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=text)]
                )
            )
            return

        tools = _tool_names(llm_request)
        fn_response = _last_function_response(llm_request)
        if "search_corpus" in tools:  # the DEBUNKER turn
            if fn_response is None:
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="search_corpus", args=self.claimset
                                )
                            )
                        ],
                    )
                )
                return
            verdicts = fn_response.response["verdicts"]
            final = {
                "verdicts": [
                    {
                        "claim": entry["claim"],
                        "verdict": entry["verdict"],
                        "rebuttal": entry.get("rebuttal")
                        or entry.get("message"),
                        "source_name": entry.get("source_name"),
                    }
                    for entry in verdicts
                ]
            }
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=json.dumps(final))]
                )
            )
            return

        # The DISPATCHER turn.
        if fn_response is None:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="DEBUNKER", args=self.claimset
                            )
                        )
                    ],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=DISPATCHER_REPLY)]
            )
        )


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


@pytest.fixture()
def fake_model():
    return DebunkingFakeModel()


@pytest.fixture()
def client(fake_model):
    service = ChatService(session_service=InMemorySessionService(), llm=fake_model)
    app = create_app(verifier=FakeVerifier(), chat_service=service)
    return TestClient(app)


def turn(client, text, *, uid="maria"):
    response = client.post(
        "/api/chat",
        json={"text": text},
        headers={"Authorization": "Bearer valid-" + uid},
    )
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    return {line["type"]: line for line in lines}, lines


def template(template_id):
    return next(
        t for t in CLAIM_TEMPLATES if t.template_id == template_id
    )


class TestDebunkerCrossesRoutingGuard:
    def test_debunker_and_its_tool_are_on_the_guard_allowlist(self):
        # Both rails refuse any tool outside ALLOWED_TOOLS; the DEBUNKER
        # tool (the auto-wrapped sub-agent) and its search_corpus tool
        # must therefore be members, or every call is refused.
        from app.guard import ALLOWED_TOOLS

        assert {"DEBUNKER", "search_corpus"} <= ALLOWED_TOOLS

    def test_debunker_carries_the_second_guard_rail(self, fake_model):
        from app.debunker import build_debunker
        from app.guard import guard_before_tool

        agent = build_debunker(fake_model)
        assert agent.before_tool_callback is guard_before_tool


class TestNotCoveredRoutesToTheMwo:
    def test_not_covered_renders_the_mwo_routing_never_a_bare_refusal(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.claimset = {
            "claims": ["sabi nila makukulong daw ako kapag tumakas ako"],
            "language": "taglish",
        }
        by_type, _ = turn(client, "Sabi nila makukulong daw ako pag tumakas")

        [entry] = by_type["verdicts"]["verdicts"]
        assert entry["verdict"] == "NOT_COVERED"
        # It ROUTES: the MWO plus a number, not a shrug.
        assert "MWO" in entry["message"]
        routing = entry["routing"]
        assert routing["authority"] == "MWO (Migrant Workers Office)"
        # Every row comes from the immutable directory, dialability-
        # filtered for her country (SA, from her Case) and re-filtered by
        # ROUTING_GUARD on the way back — the model never generated one.
        expected_rows = office_directory_rows(Country.SA)
        assert routing["rows"] == expected_rows
        assert all(
            row["channel"] != Channel.LOCAL_POLICE.value
            for row in routing["rows"]
        )
        # The message names a directory number, verbatim.
        mwo_row = next(
            row
            for row in expected_rows
            if row["channel"] == Channel.MWO.value
            and row["dial_mode"] == "dialable"
        )
        assert mwo_row["phone"] in entry["message"]

    def test_not_covered_writes_nothing_to_the_case(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.claimset = {
            "claims": ["sabi nila makukulong daw ako kapag tumakas ako"],
            "language": "taglish",
        }
        by_type, _ = turn(client, "Sabi nila makukulong daw ako pag tumakas")
        claims = by_type["case"]["case"]["claims"]
        assert not any(field.startswith("debunked_") for field in claims)


class TestFalseVerdictWritesTheCase:
    def test_false_on_a_plan_relevant_belief_lands_with_provenance(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.claimset = {
            "claims": ["may utang pa ako sa placement fee"],
            "language": "taglish",
        }
        by_type, _ = turn(client, "May utang pa daw ako sa placement fee")

        claim = by_type["case"]["case"]["claims"][
            "debunked_placement_fee_debt"
        ]
        assert claim["value"] == "FALSE"
        assert claim["source"] == "debunker"
        assert claim["confidence"] == "high"
        assert claim["at"]  # provenance timestamp for the staleness hash

    def test_extraction_claims_survive_alongside_the_debunk(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.claimset = {
            "claims": ["may utang pa ako sa placement fee"],
            "language": "taglish",
        }
        by_type, _ = turn(client, "May utang pa daw ako sa placement fee")
        claims = by_type["case"]["case"]["claims"]
        assert claims["country"]["value"] == "Saudi Arabia"
        assert claims["debunked_placement_fee_debt"]["value"] == "FALSE"


class TestTaglishDemo:
    def test_utang_sa_placement_fee_returns_false_with_the_cited_rebuttal(
        self, client, fake_model
    ):
        # Demoable (issue #47): "may utang pa ako sa placement fee"
        # returns FALSE with the cited rebuttal in her language.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.claimset = {
            "claims": ["may utang pa ako sa placement fee"],
            "language": "taglish",
        }
        by_type, lines = turn(client, "may utang pa ako sa placement fee")

        [entry] = by_type["verdicts"]["verdicts"]
        expected = template("placement_fee_debt")
        assert entry["verdict"] == "FALSE"
        assert entry["rebuttal"] == expected.rebuttal_tl
        assert entry["source_name"] == expected.citations[0].source_name
        assert entry["url"] == expected.citations[0].url
        # The reply is still DISPATCHER's voice; the verdicts line is the
        # code-owned payload the UI renders (ADR-0002).
        assert by_type["reply"]["text"] == DISPATCHER_REPLY
        assert [line["type"] for line in lines] == [
            "ack",
            "reply",
            "verdicts",
            "case",
        ]

    def test_no_verdicts_line_when_debunker_never_ran(self, fake_model):
        # A plain turn (no DEBUNKER call) must not grow a verdicts line.
        class PlainFake(DebunkingFakeModel):
            async def generate_content_async(self, llm_request, stream=False):
                config = llm_request.config
                if config and config.response_schema is not None:
                    text = self.extraction_results.pop(0)
                else:
                    text = DISPATCHER_REPLY
                yield LlmResponse(
                    content=types.Content(
                        role="model", parts=[types.Part(text=text)]
                    )
                )

        plain = PlainFake()
        plain.extraction_results.append(TAGLISH_EXTRACTION)
        service = ChatService(
            session_service=InMemorySessionService(), llm=plain
        )
        app = create_app(verifier=FakeVerifier(), chat_service=service)
        client = TestClient(app)
        _, lines = turn(client, "kumusta")
        assert [line["type"] for line in lines] == ["ack", "reply", "case"]
