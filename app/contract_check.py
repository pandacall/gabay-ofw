"""Resumable Contract Check workflow and HTTP-facing service."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.events import Event, RequestInput
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.adk.workflow import Workflow
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

APP_NAME = "gabay_ofw_contract_check"
MORE_INPUT_PROMPT = "Please tell me what is actually happening."


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Claim(StrictModel):
    topic: Literal[
        "rest_days",
        "passport",
        "overtime",
        "contract_substitution",
        "repatriation",
        "medical",
        "salary",
        "other",
    ]
    contract_says: str
    actually_happening: str
    user_quote: str


class Claims(StrictModel):
    status: Literal["complete", "in_progress", "escalate_to_crisis"]
    claims: list[Claim]
    country: str | None = None


class Finding(StrictModel):
    issue: str
    rule: str
    severity: Literal["informational", "concerning", "urgent"]


class FindingsReport(StrictModel):
    findings: list[Finding]


class ContractCheckStart(BaseModel):
    message: Annotated[str, Field(min_length=1, max_length=8000)]


class ContractCheckMessage(ContractCheckStart):
    interrupt_id: Annotated[str, Field(min_length=1, max_length=200)]


class ContractCheckInProgress(StrictModel):
    id: str
    status: Literal["in_progress"]
    prompt: str
    interrupt_id: str


class ContractCheckComplete(StrictModel):
    id: str
    status: Literal["complete"]
    report: FindingsReport


class ContractCheckEscalation(StrictModel):
    id: str
    status: Literal["escalate_to_crisis"]
    country: str | None = None


ContractCheckResponse = Annotated[
    ContractCheckInProgress | ContractCheckComplete | ContractCheckEscalation,
    Field(discriminator="status"),
]


class ContractCheckNotFoundError(Exception):
    pass


class ContractCheckNotResumableError(Exception):
    pass


class ContractCheckModelOutputError(Exception):
    pass


def _build_workflow(
    interviewer_model: BaseLlm,
    rule_matcher_model: BaseLlm,
) -> Workflow:
    interviewer = LlmAgent(
        name="interviewer",
        model=interviewer_model,
        instruction="Extract structured Claims from the user's Contract Check message.",
        output_schema=Claims,
        output_key="claims",
    )
    rule_matcher = LlmAgent(
        name="rule_matcher",
        model=rule_matcher_model,
        instruction="Produce a structured Findings Report from the complete Claims.",
        output_schema=FindingsReport,
        output_key="findings_report",
    )

    def route_claims(ctx: Context, node_input: Claims) -> Event:
        claims = Claims.model_validate(node_input)
        turn_index = int(ctx.state.get("turn_index", 0)) + 1
        return Event(
            output=claims.model_dump(mode="json"),
            route=claims.status,
            state={
                "claims": claims.model_dump(mode="json"),
                "status": claims.status,
                "turn_index": turn_index,
            },
        )

    def request_more(ctx: Context, node_input: Claims) -> RequestInput:
        return RequestInput(
            interrupt_id=f"contract-check-{ctx.session.id}-{ctx.state['turn_index']}",
            message=MORE_INPUT_PROMPT,
            response_schema=str,
        )

    def finish_report(node_input: FindingsReport) -> Event:
        report = FindingsReport.model_validate(node_input)
        output = {"status": "complete", "report": report.model_dump(mode="json")}
        return Event(
            output=output,
            state={**output, "rule_matcher_runs": 1},
        )

    def finish_escalation(node_input: Claims) -> Event:
        claims = Claims.model_validate(node_input)
        output = {
            "status": "escalate_to_crisis",
            "country": claims.country,
        }
        return Event(output=output, state=output)

    return Workflow(
        name="contract_check",
        edges=[
            ("START", interviewer),
            (interviewer, route_claims),
            (
                route_claims,
                {
                    "in_progress": request_more,
                    "complete": rule_matcher,
                    "escalate_to_crisis": finish_escalation,
                },
            ),
            (request_more, interviewer),
            (rule_matcher, finish_report),
        ],
    )


class ContractCheckService:
    def __init__(
        self,
        *,
        session_service: BaseSessionService,
        interviewer_model: BaseLlm,
        rule_matcher_model: BaseLlm,
    ) -> None:
        workflow = _build_workflow(interviewer_model, rule_matcher_model)
        app = App(
            name=APP_NAME,
            root_agent=workflow,
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        self._sessions = session_service
        self._runner = Runner(app=app, session_service=session_service)

    async def start(self, uid: str, message: str) -> dict[str, Any]:
        check_id = uuid4().hex
        await self._sessions.create_session(
            app_name=APP_NAME,
            user_id=uid,
            session_id=check_id,
            state={"status": "started", "rule_matcher_runs": 0},
        )
        try:
            result = await self._run(
                uid=uid,
                check_id=check_id,
                message=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=message)],
                ),
            )
        except ValidationError as error:
            raise ContractCheckModelOutputError from error
        return {"id": check_id, **result}

    async def resume(
        self,
        uid: str,
        check_id: str,
        interrupt_id: str,
        message: str,
    ) -> dict[str, Any]:
        session = await self._sessions.get_session(
            app_name=APP_NAME,
            user_id=uid,
            session_id=check_id,
        )
        if session is None:
            raise ContractCheckNotFoundError(check_id)
        if session.state.get("status") != "in_progress":
            raise ContractCheckNotResumableError(check_id)

        unresolved_interrupts: list[str] = []
        for event in session.events:
            unresolved_interrupts.extend(
                call.id
                for call in event.get_function_calls()
                if call.name == "adk_request_input" and call.id
            )
            for response in event.get_function_responses():
                if response.id in unresolved_interrupts:
                    unresolved_interrupts.remove(response.id)
        if not unresolved_interrupts or interrupt_id != unresolved_interrupts[-1]:
            raise ContractCheckNotResumableError(check_id)

        try:
            result = await self._run(
                uid=uid,
                check_id=check_id,
                message=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=interrupt_id,
                                name="adk_request_input",
                                response={"result": message},
                            )
                        )
                    ],
                ),
            )
        except ValidationError as error:
            raise ContractCheckModelOutputError from error
        return {"id": check_id, **result}

    async def _run(
        self,
        *,
        uid: str,
        check_id: str,
        message: types.Content,
    ) -> dict[str, Any]:
        final_output = None
        pending_input = None
        async for event in self._runner.run_async(
            user_id=uid,
            session_id=check_id,
            new_message=message,
        ):
            if event.output is not None:
                final_output = event.output
            if event.content and event.content.parts:
                for part in event.content.parts:
                    call = part.function_call
                    if call and call.name == "adk_request_input":
                        pending_input = {
                            "status": "in_progress",
                            "prompt": call.args["message"],
                            "interrupt_id": call.id,
                        }
        if pending_input is not None:
            return pending_input
        if isinstance(final_output, dict):
            return final_output
        raise RuntimeError("Contract Check workflow produced no result")
