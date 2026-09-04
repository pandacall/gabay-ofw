"""Emulator tests for the single deletion path and retention sweep (#40).

Requires the Firestore emulator (FIRESTORE_EMULATOR_HOST). The wipe
assertion is total: after panic_wipe, a recursive walk from users/{uid}
finds zero documents anywhere — session docs, event subcollections,
adkUserState, notes, and even orphaned subcollections under missing
parent documents.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.adk.events import Event, EventActions
from google.cloud import firestore

from app.deletion import DeletionReason, delete_user_subtree
from app.firestore_session_service import FirestoreSessionService
from app.retention import BASE_WINDOW, sweep_expired, touch_expire_at

pytestmark = pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"),
    reason="requires the Firestore emulator",
)

APP_NAME = "gabay-ofw"
NOW = datetime.now(timezone.utc)


def _db():
    return firestore.Client(project="gabay-ofw-rules-test")


def _event(state_delta: dict) -> Event:
    return Event(
        author="DISPATCHER",
        invocation_id=f"inv-{uuid4().hex}",
        actions=EventActions(state_delta=state_delta),
    )


def _seed_conversation(db, uid: str) -> None:
    """Seeds a realistic subtree via the session service plus raw writes."""
    service = FirestoreSessionService(db)

    async def seed():
        session = await service.create_session(
            app_name=APP_NAME,
            user_id=uid,
            state={"case_country": "SA", "user:preferred_language": "tl"},
        )
        await service.append_event(session, _event({"case_stage": "intake"}))
        await service.append_event(session, _event({"safety_flag": "set"}))

    asyncio.run(seed())
    user_ref = db.collection("users").document(uid)
    user_ref.collection("notes").document("n1").set({"text": "remittance"})
    # An orphaned events subcollection under a missing session document —
    # the wipe must find these too (stream() would skip the ghost parent).
    (
        user_ref.collection("sessions")
        .document("ghost")
        .collection("events")
        .document("e1")
        .set({"timestamp": 1})
    )


def _remaining_documents(doc_ref) -> list[str]:
    remaining = []
    if doc_ref.get().exists:
        remaining.append(doc_ref.path)
    for collection in doc_ref.collections():
        for child in collection.list_documents():
            remaining.extend(_remaining_documents(child))
    return remaining


def test_panic_wipe_leaves_zero_documents_under_the_user_subtree():
    db = _db()
    uid = f"wipe-{uuid4().hex}"
    bystander = f"bystander-{uuid4().hex}"
    # She holds several Conversations (issue #72) — delete-everything must
    # still take the whole subtree, every session doc included.
    _seed_conversation(db, uid)
    _seed_conversation(db, uid)
    _seed_conversation(db, bystander)

    result = delete_user_subtree(db, uid, reason=DeletionReason.PANIC_WIPE)

    assert result.reason is DeletionReason.PANIC_WIPE
    assert result.documents_deleted > 1
    assert _remaining_documents(db.collection("users").document(uid)) == []
    # Another user's subtree is untouched.
    assert _remaining_documents(db.collection("users").document(bystander)) != []


def test_expiry_sweep_shares_the_deletion_path_and_respects_deadlines():
    db = _db()
    expired = f"expired-{uuid4().hex}"
    active = f"active-{uuid4().hex}"
    detained = f"detained-{uuid4().hex}"
    for uid in (expired, active, detained):
        _seed_conversation(db, uid)

    stale = NOW - BASE_WINDOW - timedelta(days=30)
    # The seeding above already touched expireAt with fresh activity, so
    # force the stored values directly to model each retention situation.
    db.collection("users").document(expired).set(
        {"expireAt": stale + BASE_WINDOW}, merge=True
    )
    # A detained user's inactivity is just as stale, but a live deadline
    # keeps her evidence: the deadline component is absolute (ADR-0007).
    db.collection("users").document(detained).set(
        {"expireAt": stale + BASE_WINDOW}, merge=True
    )
    touch_expire_at(
        db,
        detained,
        last_activity=stale,
        live_deadlines=[NOW + timedelta(days=365)],
    )

    results = sweep_expired(db, now=NOW)

    swept = {result.uid for result in results if result.uid in {expired, active, detained}}
    assert swept == {expired}
    assert all(r.reason is DeletionReason.RETENTION_EXPIRY for r in results)
    assert _remaining_documents(db.collection("users").document(expired)) == []
    assert _remaining_documents(db.collection("users").document(active)) != []
    assert _remaining_documents(db.collection("users").document(detained)) != []


def test_touch_expire_at_never_shrinks_a_deadline_backed_expiry():
    db = _db()
    uid = f"touch-{uuid4().hex}"
    deadline = NOW + timedelta(days=365)

    promised = touch_expire_at(
        db, uid, last_activity=NOW, live_deadlines=[deadline]
    )
    # A later activity-only touch (no deadlines known) must not shrink it.
    after_activity = touch_expire_at(db, uid, last_activity=NOW)

    assert promised == after_activity
    stored = db.collection("users").document(uid).get().to_dict()["expireAt"]
    assert stored == promised


def test_session_activity_extends_expire_at():
    db = _db()
    uid = f"activity-{uuid4().hex}"
    _seed_conversation(db, uid)

    stored = db.collection("users").document(uid).get().to_dict()["expireAt"]
    assert stored >= NOW + BASE_WINDOW - timedelta(minutes=5)
