import asyncio

import pytest
from fastapi.testclient import TestClient
from google.adk.sessions import InMemorySessionService

from app.contract_check import ContractCheckService
from app.main import create_app
from tests.contract_check_fakes import CannedModel, FailingModel, FakeVerifier, auth


@pytest.fixture()
def interviewer():
    return CannedModel(
        responses=[
            (
                '{"status":"in_progress","claims":[],"country":null,'
                '"next_question":"What is actually happening at work?"}'
            ),
            (
                '{"status":"complete","claims":[{"topic":"rest_days",'
                '"contract_says":"One day off each week",'
                '"actually_happening":"No rest days",'
                '"user_quote":"Wala akong day off"}],"country":"SA"}'
            ),
        ]
    )


@pytest.fixture()
def rule_matcher():
    return CannedModel(
        responses=[
            (
                '{"findings":[{"issue":"No weekly rest day",'
                '"rule":"At least one rest day per week, with premium compensation if worked.",'
                '"severity":"concerning"}]}'
            )
        ]
    )


@pytest.fixture()
def client(interviewer, rule_matcher):
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=interviewer,
        rule_matcher_model=rule_matcher,
    )
    return TestClient(create_app(verifier=FakeVerifier(), contract_checks=service))


def test_start_contract_check_pauses_for_more_input(client, rule_matcher):
    response = client.post(
        "/api/contract-checks",
        json={"message": "One day off is written in my contract."},
        headers=auth("alice"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["prompt"] == "What is actually happening at work?"
    assert body["interrupt_id"].startswith("contract-check-")
    assert body["id"]
    assert rule_matcher.call_count == 0


def test_resume_contract_check_completes_and_runs_rule_matcher_once(
    client, rule_matcher
):
    started = client.post(
        "/api/contract-checks",
        json={"message": "My contract promises one day off."},
        headers=auth("alice"),
    ).json()

    response = client.post(
        f"/api/contract-checks/{started['id']}/messages",
        json={
            "message": "I actually work every day.",
            "interrupt_id": started["interrupt_id"],
        },
        headers=auth("alice"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": started["id"],
        "status": "complete",
        "report": {
            "disclaimer": (
                "These findings appear to conflict with standard POEA/DMW rules. "
                "Verify them with DMW, OWWA, or a licensed lawyer."
            ),
            "salary_guidance": (
                "For current salary minimums, visit https://dmw.gov.ph/."
            ),
            "findings": [
                {
                    "issue": "No weekly rest day",
                    "rule": (
                        "At least one rest day per week, with premium "
                        "compensation if worked."
                    ),
                    "severity": "concerning",
                }
            ]
        },
    }
    assert rule_matcher.call_count == 1

    duplicate = client.post(
        f"/api/contract-checks/{started['id']}/messages",
        json={
            "message": "I actually work every day.",
            "interrupt_id": started["interrupt_id"],
        },
        headers=auth("alice"),
    )
    assert duplicate.status_code == 409
    assert rule_matcher.call_count == 1


def test_in_progress_resume_loops_with_a_new_interrupt_id():
    interviewer = CannedModel(
        responses=[
            (
                '{"status":"in_progress","claims":[],"country":null,'
                '"next_question":"What does your contract say?"}'
            ),
            (
                '{"status":"in_progress","claims":[],"country":"AE",'
                '"next_question":"What happens in practice?"}'
            ),
            '{"status":"complete","claims":[],"country":"AE"}',
        ]
    )
    rule_matcher = CannedModel(responses=[])
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=interviewer,
        rule_matcher_model=rule_matcher,
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service)
    )

    started = client.post(
        "/api/contract-checks",
        json={"message": "My contract says I get overtime pay."},
        headers=auth("alice"),
    ).json()
    response = client.post(
        f"/api/contract-checks/{started['id']}/messages",
        json={
            "message": "I work beyond eight hours.",
            "interrupt_id": started["interrupt_id"],
        },
        headers=auth("alice"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["interrupt_id"] != started["interrupt_id"]
    assert rule_matcher.call_count == 0

    stale_resume = client.post(
        f"/api/contract-checks/{started['id']}/messages",
        json={
            "message": "Replaying an old response",
            "interrupt_id": started["interrupt_id"],
        },
        headers=auth("alice"),
    )
    assert stale_resume.status_code == 409
    assert interviewer.call_count == 2


def test_escalation_ends_without_calling_rule_matcher():
    interviewer = CannedModel(
        responses=[
            (
                '{"status":"escalate_to_crisis","claims":[{"topic":"passport",'
                '"contract_says":"I keep my passport",'
                '"actually_happening":"My employer locked it away",'
                '"user_quote":"Hindi ako makaalis"}],"country":"QA"}'
            )
        ]
    )
    rule_matcher = CannedModel(responses=[])
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=interviewer,
        rule_matcher_model=rule_matcher,
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service)
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "My employer has my passport and I cannot leave."},
        headers=auth("alice"),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "escalate_to_crisis"
    assert response.json()["country"] == "QA"
    assert "interrupt_id" not in response.json()
    assert rule_matcher.call_count == 0


def test_malformed_model_output_is_rejected_and_not_persisted():
    sessions = InMemorySessionService()
    service = ContractCheckService(
        session_service=sessions,
        interviewer_model=CannedModel(responses=['{"claims":[]}']),
        rule_matcher_model=CannedModel(responses=[]),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my rest days."},
        headers=auth("alice"),
    )

    assert response.status_code == 502
    assert response.headers["x-request-id"]
    assert response.headers["x-request-id"] in response.json()["detail"]
    listed = asyncio.run(
        sessions.list_sessions(app_name="gabay_ofw_contract_check", user_id="alice")
    )
    session = asyncio.run(
        sessions.get_session(
            app_name="gabay_ofw_contract_check",
            user_id="alice",
            session_id=listed.sessions[0].id,
        )
    )
    assert session is not None
    assert "claims" not in session.state
    assert '{"claims":[]}' not in session.model_dump_json()


def test_contract_check_endpoints_require_authentication(client):
    started = client.post(
        "/api/contract-checks",
        json={"message": "Please check my contract."},
    )
    resumed = client.post(
        "/api/contract-checks/check-id/messages",
        json={"message": "More detail", "interrupt_id": "interrupt-id"},
    )

    assert started.status_code == 401
    assert resumed.status_code == 401


def test_gemini_rate_limit_returns_safe_diagnostic():
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=FailingModel(status_code=429),
        rule_matcher_model=CannedModel(responses=[]),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my contract."},
        headers=auth("alice"),
    )

    assert response.status_code == 503
    assert response.headers["x-request-id"]
    assert response.json()["detail"] == (
        "Gemini is temporarily unavailable. "
        f"Reference: {response.headers['x-request-id']}"
    )
    assert "provider detail" not in response.text


def test_malformed_rule_matcher_output_is_rejected_and_not_persisted():
    sessions = InMemorySessionService()
    service = ContractCheckService(
        session_service=sessions,
        interviewer_model=CannedModel(
            responses=['{"status":"complete","claims":[],"country":"SA"}']
        ),
        rule_matcher_model=CannedModel(
            responses=['{"findings":[{"severity":"unknown"}]}']
        ),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my contract."},
        headers=auth("alice"),
    )

    assert response.status_code == 502
    listed = asyncio.run(
        sessions.list_sessions(app_name="gabay_ofw_contract_check", user_id="alice")
    )
    session = asyncio.run(
        sessions.get_session(
            app_name="gabay_ofw_contract_check",
            user_id="alice",
            session_id=listed.sessions[0].id,
        )
    )
    assert session is not None
    assert "findings_report" not in session.state
    assert '"severity":"unknown"' not in session.model_dump_json()


def test_ungrounded_rule_matcher_output_is_rejected():
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=CannedModel(
            responses=['{"status":"complete","claims":[],"country":"SA"}']
        ),
        rule_matcher_model=CannedModel(
            responses=[
                (
                    '{"findings":[{"issue":"Low pay",'
                    '"rule":"Saudi law requires a monthly salary of 1500 SAR.",'
                    '"severity":"urgent"}]}'
                )
            ]
        ),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my salary."},
        headers=auth("alice"),
    )

    assert response.status_code == 502


def test_salary_figure_in_rule_matcher_output_is_rejected():
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=CannedModel(
            responses=['{"status":"complete","claims":[],"country":"SA"}']
        ),
        rule_matcher_model=CannedModel(
            responses=[
                (
                    '{"findings":[{"issue":"Salary is only 1500 SAR",'
                    '"rule":"Overtime must be compensated under the verified employment contract.",'
                    '"severity":"concerning"}]}'
                )
            ]
        ),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my salary."},
        headers=auth("alice"),
    )

    assert response.status_code == 502


def test_salary_figure_in_interviewer_question_is_rejected():
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=CannedModel(
            responses=[
                (
                    '{"status":"in_progress","claims":[],"country":"SA",'
                    '"next_question":"Does your contract promise a salary of 1500 per month?"}'
                )
            ]
        ),
        rule_matcher_model=CannedModel(responses=[]),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my salary."},
        headers=auth("alice"),
    )

    assert response.status_code == 502


def test_non_salary_figure_in_interviewer_question_is_allowed():
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=CannedModel(
            responses=[
                (
                    '{"status":"in_progress","claims":[],"country":"SA",'
                    '"next_question":"Do you usually work 12 hours each day?"}'
                )
            ]
        ),
        rule_matcher_model=CannedModel(responses=[]),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my overtime."},
        headers=auth("alice"),
    )

    assert response.status_code == 201
    assert response.json()["prompt"] == "Do you usually work 12 hours each day?"


def test_non_iso_country_code_is_rejected():
    service = ContractCheckService(
        session_service=InMemorySessionService(),
        interviewer_model=CannedModel(
            responses=['{"status":"in_progress","claims":[],"country":"Saudi Arabia"}']
        ),
        rule_matcher_model=CannedModel(responses=[]),
    )
    client = TestClient(
        create_app(verifier=FakeVerifier(), contract_checks=service),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/contract-checks",
        json={"message": "Please check my contract."},
        headers=auth("alice"),
    )

    assert response.status_code == 502
