"""Firestore-backed ADK sessions under the v6 user-scoped paths (ADR-0003).

Storage layout:

    users/{uid}/sessions/{sessionId}              — session doc: appName,
        session-scoped state, revision, lastUpdateTime
    users/{uid}/sessions/{sessionId}/events/{id}  — event subcollection,
        monotonic by timestamp
    users/{uid}/adkUserState/{appName}            — ``user:``-scoped state
    adkAppState/{appName}                         — ``app:``-scoped state

``temp:``-scoped state is never persisted. The session doc carries a
``revision`` counter: append_event is transactional, raises
``StaleSessionError`` when the in-memory session lost a concurrency race,
and retries exactly once by re-reading storage and re-applying only this
event's delta — a concurrent turn may have written a safety flag, so the
stored state is never blindly overwritten.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from google.adk.errors import StaleSessionError
from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.errors.session_not_found_error import SessionNotFoundError
from google.adk.events import Event
from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import (
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.sessions.state import State
from google.cloud import firestore

from app.retention import touch_expire_at
from app.deletion import delete_document_tree

_STALE_SESSION_ERROR_MESSAGE = (
    "The session has been modified in storage since it was loaded. "
    "Please reload the session before appending more events."
)


def _split_state(state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Splits state into app/user/session buckets; ``temp:`` keys are dropped."""
    buckets: dict[str, dict[str, Any]] = {"app": {}, "user": {}, "session": {}}
    for key, value in (state or {}).items():
        if key.startswith(State.APP_PREFIX):
            buckets["app"][key.removeprefix(State.APP_PREFIX)] = value
        elif key.startswith(State.USER_PREFIX):
            buckets["user"][key.removeprefix(State.USER_PREFIX)] = value
        elif not key.startswith(State.TEMP_PREFIX):
            buckets["session"][key] = value
    return buckets


def _merge_state(
    app_state: dict[str, Any] | None,
    user_state: dict[str, Any] | None,
    session_state: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(session_state)
    for key, value in (app_state or {}).items():
        merged[State.APP_PREFIX + key] = value
    for key, value in (user_state or {}).items():
        merged[State.USER_PREFIX + key] = value
    return merged


class FirestoreSessionService(BaseSessionService):
    """Persists ADK sessions to the v6 contract paths with revision checks."""

    def __init__(self, db) -> None:
        self._db = db

    def _sessions_ref(self, user_id: str):
        return self._db.collection("users").document(user_id).collection("sessions")

    def _session_ref(self, user_id: str, session_id: str):
        return self._sessions_ref(user_id).document(session_id)

    def _user_state_ref(self, user_id: str, app_name: str):
        return (
            self._db.collection("users")
            .document(user_id)
            .collection("adkUserState")
            .document(app_name)
        )

    def _app_state_ref(self, app_name: str):
        return self._db.collection("adkAppState").document(app_name)

    async def _touch_retention(self, user_id: str, activity_ts: float) -> None:
        """Extends users/{uid}.expireAt for this activity (ADR-0007).

        Deadlines are supplied by the Plan-publishing path when it lands;
        touch_expire_at is monotonic, so an activity-only touch can never
        shrink a deadline-backed expiry already stored."""
        last_activity = datetime.fromtimestamp(activity_ts, tz=timezone.utc)
        await asyncio.to_thread(
            touch_expire_at, self._db, user_id, last_activity=last_activity
        )

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        session_id = session_id or uuid4().hex
        buckets = _split_state(state)
        session_ref = self._session_ref(user_id, session_id)
        app_ref = self._app_state_ref(app_name)
        user_ref = self._user_state_ref(user_id, app_name)
        now = time.time()

        def persist() -> tuple[dict[str, Any], dict[str, Any]]:
            transaction = self._db.transaction()

            @firestore.transactional
            def create_txn(txn) -> tuple[dict[str, Any], dict[str, Any]]:
                if session_ref.get(transaction=txn).exists:
                    raise AlreadyExistsError(
                        f"Session with id {session_id} already exists."
                    )
                stored_app = app_ref.get(transaction=txn).to_dict() or {}
                stored_user = user_ref.get(transaction=txn).to_dict() or {}
                if buckets["app"]:
                    stored_app.update(buckets["app"])
                    txn.set(app_ref, stored_app, merge=True)
                if buckets["user"]:
                    stored_user.update(buckets["user"])
                    txn.set(user_ref, stored_user, merge=True)
                txn.set(
                    session_ref,
                    {
                        "appName": app_name,
                        "state": buckets["session"],
                        "revision": 0,
                        "lastUpdateTime": now,
                    },
                )
                return stored_app, stored_user

            return create_txn(transaction)

        stored_app, stored_user = await asyncio.to_thread(persist)
        await self._touch_retention(user_id, now)
        session = Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=_merge_state(stored_app, stored_user, buckets["session"]),
            last_update_time=now,
        )
        session._storage_update_marker = "0"
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        session_ref = self._session_ref(user_id, session_id)

        def read():
            snapshot = session_ref.get()
            if not snapshot.exists:
                return None
            data = snapshot.to_dict()
            if data.get("appName") != app_name:
                return None
            event_snapshots = list(
                session_ref.collection("events").order_by("timestamp").stream()
            )
            events = [
                Event.model_validate(item.to_dict()["event"])
                for item in event_snapshots
            ]
            app_state = self._app_state_ref(app_name).get().to_dict() or {}
            user_state = (
                self._user_state_ref(user_id, app_name).get().to_dict() or {}
            )
            return data, events, app_state, user_state

        result = await asyncio.to_thread(read)
        if result is None:
            return None
        data, events, app_state, user_state = result

        if config:
            if config.after_timestamp is not None:
                events = [
                    event
                    for event in events
                    if event.timestamp >= config.after_timestamp
                ]
            if config.num_recent_events is not None:
                events = (
                    []
                    if config.num_recent_events == 0
                    else events[-config.num_recent_events :]
                )
        session = Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=_merge_state(app_state, user_state, data.get("state", {})),
            events=events,
            last_update_time=data.get("lastUpdateTime", 0.0),
        )
        session._storage_update_marker = str(data.get("revision", 0))
        return session

    async def list_sessions(
        self, *, app_name: str, user_id: str | None = None
    ) -> ListSessionsResponse:
        if user_id is None:
            raise ValueError("Firestore sessions must always be scoped to a user")
        collection = self._sessions_ref(user_id)
        snapshots = await asyncio.to_thread(lambda: list(collection.stream()))
        sessions = [
            Session(
                app_name=app_name,
                user_id=user_id,
                id=snapshot.id,
                last_update_time=snapshot.to_dict().get("lastUpdateTime", 0.0),
            )
            for snapshot in snapshots
            if snapshot.to_dict().get("appName") == app_name
        ]
        sessions.sort(key=lambda session: session.last_update_time)
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        ref = self._session_ref(user_id, session_id)
        # Same recursive tree delete the wipe/expiry path is built on —
        # a session delete must never orphan its events subcollection.
        await asyncio.to_thread(delete_document_tree, ref)

    def _read_revision(self, session_ref) -> int:
        """Re-reads the stored revision when retrying a stale append."""
        snapshot = session_ref.get()
        if not snapshot.exists:
            raise SessionNotFoundError(f"Session {session_ref.id} not found.")
        return (snapshot.to_dict() or {}).get("revision", 0)

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event
        # Mirror DatabaseSessionService ordering: apply temp state to the
        # in-memory session first, then trim it so it is never persisted.
        self._apply_temp_state(session, event)
        event = self._trim_temp_delta_state(event)

        deltas = _split_state(
            event.actions.state_delta
            if event.actions and event.actions.state_delta
            else {}
        )
        session_ref = self._session_ref(session.user_id, session.id)
        app_ref = self._app_state_ref(session.app_name)
        user_ref = self._user_state_ref(session.user_id, session.app_name)
        event_ref = session_ref.collection("events").document(
            f"{event.timestamp:020.6f}-{uuid4().hex}"
        )
        event_payload = {
            "timestamp": event.timestamp,
            "event": event.model_dump(mode="json", by_alias=True),
        }

        def run_attempt(
            expected_revision: int | None,
        ) -> tuple[int, dict[str, Any]]:
            transaction = self._db.transaction()

            @firestore.transactional
            def append_txn(txn) -> tuple[int, dict[str, Any]]:
                snapshot = session_ref.get(transaction=txn)
                if not snapshot.exists:
                    raise SessionNotFoundError(f"Session {session.id} not found.")
                data = snapshot.to_dict() or {}
                current_revision = data.get("revision", 0)
                if (
                    expected_revision is not None
                    and expected_revision != current_revision
                ):
                    raise StaleSessionError(_STALE_SESSION_ERROR_MESSAGE)
                app_snapshot = (
                    app_ref.get(transaction=txn) if deltas["app"] else None
                )
                user_snapshot = (
                    user_ref.get(transaction=txn) if deltas["user"] else None
                )

                if app_snapshot is not None:
                    stored_app = app_snapshot.to_dict() or {}
                    stored_app.update(deltas["app"])
                    txn.set(app_ref, stored_app, merge=True)
                if user_snapshot is not None:
                    stored_user = user_snapshot.to_dict() or {}
                    stored_user.update(deltas["user"])
                    txn.set(user_ref, stored_user, merge=True)

                # Merge only this event's delta onto the freshly read stored
                # state — never overwrite with the in-memory copy, which may
                # predate a concurrent turn's safety flag.
                stored_state = data.get("state") or {}
                stored_state.update(deltas["session"])
                txn.set(
                    session_ref,
                    {
                        "appName": session.app_name,
                        "state": stored_state,
                        "revision": current_revision + 1,
                        "lastUpdateTime": event.timestamp,
                    },
                )
                txn.set(event_ref, event_payload)
                return current_revision + 1, stored_state

            return append_txn(transaction)

        marker = session._storage_update_marker
        expected = int(marker) if marker is not None else None
        try:
            new_revision, stored_state = await asyncio.to_thread(
                run_attempt, expected
            )
        except StaleSessionError:
            # A concurrent turn advanced the session. Re-read storage and
            # retry once; a second loss propagates StaleSessionError so a
            # state delta is never silently dropped.
            refreshed = await asyncio.to_thread(self._read_revision, session_ref)
            new_revision, stored_state = await asyncio.to_thread(
                run_attempt, refreshed
            )
            # Surface the concurrent turn's writes in the in-memory session.
            session.state.update(stored_state)

        await self._touch_retention(session.user_id, event.timestamp)
        await super().append_event(session, event)
        session.last_update_time = event.timestamp
        session._storage_update_marker = str(new_revision)
        return event
