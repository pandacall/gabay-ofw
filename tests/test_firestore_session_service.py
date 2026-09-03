"""Emulator tests for the v6 Firestore session service contract.

Requires the Firestore emulator (FIRESTORE_EMULATOR_HOST). Covers the
issue #37 acceptance criteria: the persistence round-trip (a Case field
survives an instance recycle, ``temp:`` state never persists), scoped
state living off the session document, the concurrent-write retry that
never clobbers a safety flag, and a failed append surfacing an error
instead of silently dropping a state delta.
"""

import asyncio
import os
from uuid import uuid4

import pytest
from google.adk.errors import StaleSessionError
from google.adk.errors.session_not_found_error import SessionNotFoundError
from google.adk.events import Event, EventActions
from google.cloud import firestore

from app.firestore_session_service import FirestoreSessionService

pytestmark = pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"),
    reason="requires the Firestore emulator",
)

APP_NAME = "gabay-ofw"


def _db():
    return firestore.Client(project="gabay-ofw-rules-test")


def _event(state_delta: dict) -> Event:
    return Event(
        author="DISPATCHER",
        invocation_id=f"inv-{uuid4().hex}",
        actions=EventActions(state_delta=state_delta),
    )


def test_round_trip_survives_recycle_and_never_persists_temp_state():
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"round-trip-{uuid4().hex}"

    async def scenario() -> str:
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        await service.append_event(
            session,
            _event(
                {
                    "case_country": "SA",
                    "temp:extraction_scratch": "raw narrative text",
                    "user:preferred_language": "tl",
                }
            ),
        )
        # The temp value is visible in memory for the rest of the invocation.
        assert session.state["temp:extraction_scratch"] == "raw narrative text"
        session_id = session.id
        del session  # simulate the instance recycle

        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )
        assert resumed is not None
        assert resumed.state["case_country"] == "SA"
        assert "temp:extraction_scratch" not in resumed.state
        assert resumed.state["user:preferred_language"] == "tl"
        assert len(resumed.events) == 1
        return session_id

    session_id = asyncio.run(scenario())

    session_doc = (
        db.collection("users")
        .document(uid)
        .collection("sessions")
        .document(session_id)
        .get()
        .to_dict()
    )
    # Scoped keys live off the session document; temp: was never written.
    assert session_doc["state"] == {"case_country": "SA"}
    assert session_doc["revision"] == 1
    user_state = (
        db.collection("users")
        .document(uid)
        .collection("adkUserState")
        .document(APP_NAME)
        .get()
        .to_dict()
    )
    assert user_state == {"preferred_language": "tl"}
    # The old Contract Check collection path is never written.
    old_path = db.collection("users").document(uid).collection("contractChecks")
    assert list(old_path.stream()) == []


def test_stale_append_retries_once_and_preserves_concurrent_safety_flag():
    service = FirestoreSessionService(_db())
    uid = f"stale-retry-{uuid4().hex}"

    async def scenario():
        created = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer_a = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        writer_b = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        # A concurrent turn writes a safety flag first.
        await service.append_event(
            writer_a, _event({"safety_flag": "PHYSICAL_ASSAULT_ONGOING"})
        )
        # writer_b is now stale; the retry path must re-apply its delta on
        # top of the flag, never overwrite it.
        await service.append_event(writer_b, _event({"case_country": "SA"}))

        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        assert resumed.state["safety_flag"] == "PHYSICAL_ASSAULT_ONGOING"
        assert resumed.state["case_country"] == "SA"
        assert len(resumed.events) == 2
        # The retried writer's in-memory session picked up the flag too.
        assert writer_b.state["safety_flag"] == "PHYSICAL_ASSAULT_ONGOING"

    asyncio.run(scenario())


def test_append_surfaces_stale_error_when_retry_also_loses(monkeypatch):
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"stale-exhausted-{uuid4().hex}"

    async def scenario():
        created = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        rival = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        await service.append_event(
            rival, _event({"safety_flag": "PHYSICAL_ASSAULT_ONGOING"})
        )

        # Another turn keeps landing between the retry's re-read and its
        # transaction, so the single retry also loses the race.
        original_read = service._read_revision

        def racing_read(session_ref):
            revision = original_read(session_ref)
            session_ref.update({"revision": firestore.Increment(1)})
            return revision

        monkeypatch.setattr(service, "_read_revision", racing_read)

        with pytest.raises(StaleSessionError):
            await service.append_event(writer, _event({"case_country": "SA"}))

        monkeypatch.setattr(service, "_read_revision", original_read)
        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        # The failed append surfaced the error without half-applying its
        # delta or clobbering the concurrent write.
        assert "case_country" not in resumed.state
        assert resumed.state["safety_flag"] == "PHYSICAL_ASSAULT_ONGOING"
        assert len(resumed.events) == 1

    asyncio.run(scenario())


def test_append_to_deleted_session_surfaces_error():
    service = FirestoreSessionService(_db())
    uid = f"deleted-append-{uuid4().hex}"

    async def scenario():
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        await service.delete_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        with pytest.raises(SessionNotFoundError):
            await service.append_event(session, _event({"case_country": "SA"}))

    asyncio.run(scenario())


def test_partial_event_is_not_persisted():
    service = FirestoreSessionService(_db())
    uid = f"partial-{uuid4().hex}"

    async def scenario():
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        event = _event({"case_country": "SA"})
        event.partial = True
        await service.append_event(session, event)
        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        assert resumed.events == []
        assert "case_country" not in resumed.state

    asyncio.run(scenario())
