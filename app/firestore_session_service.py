"""Firestore-backed ADK sessions under user-scoped Contract Check paths."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.events import Event
from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import (
    GetSessionConfig,
    ListSessionsResponse,
)
from google.api_core.exceptions import AlreadyExists as FirestoreAlreadyExists


class FirestoreSessionService(BaseSessionService):
    """Persists the ADK methods exercised by the resumable Contract Check."""

    def __init__(self, db) -> None:
        self._db = db

    def _session_ref(self, user_id: str, session_id: str):
        return (
            self._db.collection("users")
            .document(user_id)
            .collection("contractChecks")
            .document(session_id)
        )

    @staticmethod
    def _session_data(session: Session) -> dict[str, Any]:
        return {
            "appName": session.app_name,
            "state": session.state,
            "status": session.state.get("status", "started"),
            "lastUpdateTime": session.last_update_time,
        }

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        session = Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id or uuid4().hex,
            state=state or {},
        )
        ref = self._session_ref(user_id, session.id)
        try:
            await asyncio.to_thread(ref.create, self._session_data(session))
        except FirestoreAlreadyExists as error:
            raise AlreadyExistsError(
                f"Session with id {session.id} already exists."
            ) from error
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        ref = self._session_ref(user_id, session_id)
        snapshot = await asyncio.to_thread(ref.get)
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data.get("appName") != app_name:
            return None

        event_snapshots = await asyncio.to_thread(
            lambda: list(ref.collection("messages").order_by("timestamp").stream())
        )
        events = [Event.model_validate(item.to_dict()["event"]) for item in event_snapshots]
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
        return Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=data.get("state", {}),
            events=events,
            last_update_time=data.get("lastUpdateTime", 0.0),
        )

    async def list_sessions(
        self, *, app_name: str, user_id: str | None = None
    ) -> ListSessionsResponse:
        if user_id is None:
            raise ValueError("Firestore sessions must always be scoped to a user")
        collection = (
            self._db.collection("users")
            .document(user_id)
            .collection("contractChecks")
        )
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

        def delete_documents() -> None:
            for event in ref.collection("messages").stream():
                event.reference.delete()
            ref.delete()

        await asyncio.to_thread(delete_documents)

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event
        stored_event = await super().append_event(session, event)
        session.last_update_time = stored_event.timestamp
        ref = self._session_ref(session.user_id, session.id)
        event_ref = ref.collection("messages").document(
            f"{stored_event.timestamp:020.6f}-{uuid4().hex}"
        )

        def persist() -> None:
            batch = self._db.batch()
            batch.set(
                event_ref,
                {
                    "timestamp": stored_event.timestamp,
                    "event": stored_event.model_dump(mode="json", by_alias=True),
                },
            )
            batch.set(ref, self._session_data(session), merge=True)
            batch.commit()

        await asyncio.to_thread(persist)
        return stored_event
