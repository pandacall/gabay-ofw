from collections.abc import AsyncGenerator
import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.cloud import firestore
from google.genai import types

from app.contract_check import ContractCheckService
from app.firestore_session_service import FirestoreSessionService
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"),
    reason="requires the Firestore emulator",
)


class FakeVerifier:
    def verify(self, token: str) -> str:
        if not token.startswith("valid-"):
            raise HTTPException(status_code=401, detail="Invalid token")
        return token.removeprefix("valid-")


class CannedModel(BaseLlm):
    model: str = "canned"
    responses: list[str]
    call_count: int = 0

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        response = self.responses[self.call_count]
        self.call_count += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=response)],
            )
        )


def auth(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{uid}"}


def test_new_app_instance_resumes_contract_check_from_firestore():
    db = firestore.Client(project="gabay-ofw-rules-test")
    uid = "firestore-resume-user"
    started_service = ContractCheckService(
        session_service=FirestoreSessionService(db),
        interviewer_model=CannedModel(
            responses=['{"status":"in_progress","claims":[],"country":"KW"}']
        ),
        rule_matcher_model=CannedModel(responses=[]),
    )
    started_client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=started_service)
    )
    started = started_client.post(
        "/api/contract-checks",
        json={"message": "My contract says I have a rest day."},
        headers=auth(uid),
    ).json()

    matcher = CannedModel(
        responses=[
            (
                '{"findings":[{"issue":"No weekly rest day",'
                '"rule":"Minimum 1 rest day per week; premium pay if worked.",'
                '"severity":"concerning"}]}'
            )
        ]
    )
    resumed_service = ContractCheckService(
        session_service=FirestoreSessionService(db),
        interviewer_model=CannedModel(
            responses=[
                (
                    '{"status":"complete","claims":[{"topic":"rest_days",'
                    '"contract_says":"One day off each week",'
                    '"actually_happening":"No rest days",'
                    '"user_quote":"Wala akong day off"}],"country":"KW"}'
                )
            ]
        ),
        rule_matcher_model=matcher,
    )
    resumed_client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=resumed_service)
    )
    foreign_user = resumed_client.post(
        f"/api/contract-checks/{started['id']}/messages",
        json={
            "message": "This is not my check.",
            "interrupt_id": started["interrupt_id"],
        },
        headers=auth("another-user"),
    )
    assert foreign_user.status_code == 404

    response = resumed_client.post(
        f"/api/contract-checks/{started['id']}/messages",
        json={
            "message": "I actually work every day.",
            "interrupt_id": started["interrupt_id"],
        },
        headers=auth(uid),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    assert matcher.call_count == 1

    check = (
        db.collection("users")
        .document(uid)
        .collection("contractChecks")
        .document(started["id"])
    )
    assert check.get().to_dict()["state"]["status"] == "complete"
    assert len(list(check.collection("messages").stream())) > 0


def test_malformed_output_is_not_persisted_in_firestore():
    db = firestore.Client(project="gabay-ofw-rules-test")
    uid = "firestore-invalid-output-user"
    service = ContractCheckService(
        session_service=FirestoreSessionService(db),
        interviewer_model=CannedModel(responses=['{"claims":[]}']),
        rule_matcher_model=CannedModel(responses=[]),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my contract."},
        headers=auth(uid),
    )

    assert response.status_code == 502
    checks = list(
        db.collection("users")
        .document(uid)
        .collection("contractChecks")
        .stream()
    )
    assert len(checks) == 1
    check = checks[0]
    assert "claims" not in check.to_dict()["state"]
    persisted = [
        event.to_dict()["event"]
        for event in check.reference.collection("messages").stream()
    ]
    assert '{"claims":[]}' not in str(persisted)
