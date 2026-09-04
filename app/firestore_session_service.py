"""Firestore-backed ADK sessions under the v6 user-scoped paths (ADR-0003).

Storage layout:

    users/{uid}/sessions/{sessionId}              — session doc: appName,
        session-scoped state, revision, lastUpdateTime
    users/{uid}/sessions/{sessionId}/events/{id}  — event subcollection,
        monotonic by timestamp
    users/{uid}/adkUserState/{appName}            — ``user:``-scoped state,
        including the Case and the Plan (ADR-0008: one per user, never
        per Conversation)
    adkAppState/{appName}                         — ``app:``-scoped state

``temp:``-scoped state is never persisted. The session doc carries a
``revision`` counter: append_event is transactional, raises
``StaleSessionError`` when the in-memory session lost a concurrency race,
and retries exactly once by re-reading storage and re-applying only this
event's delta — a concurrent turn may have written a safety flag, so the
stored state is never blindly overwritten.

The Case and the Plan get a STRONGER guarantee than that revision check:
``event.actions.state_delta`` may carry ``app.state_keys.CASE_MUTATIONS``
/ ``PLAN_MUTATIONS`` (``temp:``-scoped so ADK never persists them
directly). ``append_event`` reads them back out of the RAW delta before
the ``temp:`` strip, and re-runs ``app.case.apply_mutations`` /
``app.plan_ops.apply_mutations`` INSIDE the same transaction, against the
Case/Plan actually read from ``adkUserState`` this attempt — never
trusting a merged blob some caller also placed on the delta as a
same-turn in-memory convenience. This is what closes the lost-update bug
where a DISPATCHER turn already in flight when she taps EMERGENCY would
otherwise commit a Case computed before the tap and silently erase the
press (ADR-0008).
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
from google.adk.events import Event, EventActions
from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import (
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.sessions.state import State
from google.cloud import firestore

from app.retention import touch_expire_at
from app.deletion import delete_document_tree
from app.case import apply_mutations as apply_case_mutations
from app.labels import LISTING_STATE_KEYS
from app.plan_ops import apply_mutations as apply_plan_mutations
from app.state_keys import (
    CASE,
    CASE_MUTATIONS,
    CASE_RAW,
    PLAN,
    PLAN_ACTIVE,
    PLAN_ACTIVE_RAW,
    PLAN_MUTATIONS,
    PLAN_RAW,
    PLAN_SEQ_IN,
    PLAN_SEQ_IN_RAW,
)

_STALE_SESSION_ERROR_MESSAGE = (
    "The session has been modified in storage since it was loaded. "
    "Please reload the session before appending more events."
)

#: Raw (unprefixed) <-> user-prefixed key pairs for the fields a Case or
#: Plan mutation replay may touch — used to reconcile in-memory
#: session state and the event's own recorded delta to whatever actually
#: landed in ``adkUserState`` this attempt.
_MUTATION_RAW_TO_PREFIXED = (
    (CASE_RAW, CASE),
    (PLAN_RAW, PLAN),
    (PLAN_SEQ_IN_RAW, PLAN_SEQ_IN),
    (PLAN_ACTIVE_RAW, PLAN_ACTIVE),
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


def _plan_state_from(stored_user: dict[str, Any]) -> dict[str, Any]:
    """The ``{"plan", "plan_seq_in", "plan_active"}`` bundle
    ``app.plan_ops`` operates on, read from a raw ``adkUserState`` dict."""
    return {
        "plan": stored_user.get(PLAN_RAW),
        "plan_seq_in": stored_user.get(PLAN_SEQ_IN_RAW),
        "plan_active": stored_user.get(PLAN_ACTIVE_RAW),
    }


def _write_plan_state(stored_user: dict[str, Any], plan_state: dict[str, Any]) -> None:
    stored_user[PLAN_RAW] = plan_state["plan"]
    stored_user[PLAN_SEQ_IN_RAW] = plan_state["plan_seq_in"]
    stored_user[PLAN_ACTIVE_RAW] = plan_state["plan_active"]


def _replay_case_mutations(
    stored_user: dict[str, Any],
    fresh_case: Any,
    mutations: list[dict[str, Any]] | None,
    *,
    force: bool = False,
) -> bool:
    """Replays ``mutations`` against ``fresh_case`` and writes the result
    onto ``stored_user[CASE_RAW]`` — but only when something actually
    changed, or ``force`` says so. An all-unrecognised mutation list must
    leave the stored Case truly UNTOUCHED, never rewritten to an
    identical value (which, from empty state, would otherwise plant a
    ``case: null`` field where none existed). ``force=True`` is for
    ``append_event``: a same-turn pre-merged blob on the raw delta must
    be overridden back to the replayed value even when replay itself was
    a no-op, or that stale blob would silently win. Returns whether
    ``stored_user`` was written to.
    """
    if not mutations:
        return False
    new_case = apply_case_mutations(fresh_case, mutations)
    if new_case == fresh_case and not force:
        return False
    stored_user[CASE_RAW] = new_case
    return True


def _replay_plan_mutations(
    stored_user: dict[str, Any],
    fresh_plan_state: dict[str, Any],
    mutations: list[dict[str, Any]] | None,
    *,
    force: bool = False,
) -> bool:
    """The Plan analogue of ``_replay_case_mutations``. Returns whether
    ``stored_user`` was written to."""
    if not mutations:
        return False
    new_plan_state = apply_plan_mutations(fresh_plan_state, mutations)
    if new_plan_state == fresh_plan_state and not force:
        return False
    _write_plan_state(stored_user, new_plan_state)
    return True


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

    async def get_user_state(
        self, *, app_name: str, user_id: str
    ) -> dict[str, Any]:
        """Reads ``users/{uid}/adkUserState/{appName}`` directly, with NO
        Session involved (ADR-0008): the Case and the Plan belong to her,
        not to any one Conversation, so a caller like the EMERGENCY
        button or ``mark_safe`` — which used to fall back to
        ``list_sessions`` just to find "her" session — can read (or, via
        ``append_user_mutation``, write) her Case without ever touching
        a session at all. Returns raw (unprefixed) keys, e.g. ``"case"``
        rather than ``"user:case"``, matching ``BaseSessionService``'s
        contract. Empty dict when nothing has been stored yet.
        """

        def read() -> dict[str, Any]:
            snapshot = self._user_state_ref(user_id, app_name).get()
            return snapshot.to_dict() or {}

        return await asyncio.to_thread(read)

    async def append_user_mutation(
        self,
        *,
        app_name: str,
        user_id: str,
        case_mutations: list[dict[str, Any]] | None = None,
        plan_mutations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Applies Case and/or Plan mutations directly to
        ``adkUserState``, with NO Session read, created, or touched at
        all (ADR-0008). Used by the EMERGENCY button, ``mark_safe``, and
        the one-tap correction — none of which own, or need, a
        Conversation. Runs inside the same kind of transaction
        ``append_event`` uses, against the freshly-read stored Case/Plan.

        Returns the resulting raw ``adkUserState`` dict (unprefixed
        keys) so callers can pull ``"case"`` straight out of it.
        """
        user_ref = self._user_state_ref(user_id, app_name)

        def persist() -> dict[str, Any]:
            transaction = self._db.transaction()

            @firestore.transactional
            def mutate_txn(txn) -> dict[str, Any]:
                snapshot = user_ref.get(transaction=txn)
                stored_user = snapshot.to_dict() or {}
                _replay_case_mutations(
                    stored_user, stored_user.get(CASE_RAW), case_mutations
                )
                _replay_plan_mutations(
                    stored_user, _plan_state_from(stored_user), plan_mutations
                )
                txn.set(user_ref, stored_user, merge=True)
                return stored_user

            return mutate_txn(transaction)

        stored_user = await asyncio.to_thread(persist)
        await self._touch_retention(user_id, time.time())
        return stored_user

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
                # Just the denormalised label keys (issue #73), projected
                # from the session document this stream already fetched —
                # no extra read, and nothing broader than the rail needs.
                # The per-user Case/Plan and the events are not loaded.
                state={
                    key: value
                    for key, value in (snapshot.to_dict().get("state") or {}).items()
                    if key in LISTING_STATE_KEYS
                },
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
        # Capture this event's recorded Case/Plan mutations from the RAW
        # state delta BEFORE _trim_temp_delta_state strips every temp:
        # key (ADR-0008) — they must survive the strip to be replayed
        # inside the transaction below, even though they are never
        # themselves persisted.
        raw_delta = (
            event.actions.state_delta
            if event.actions and event.actions.state_delta
            else {}
        )
        case_mutations = raw_delta.get(CASE_MUTATIONS)
        plan_mutations = raw_delta.get(PLAN_MUTATIONS)

        # Mirror DatabaseSessionService ordering: apply temp state to the
        # in-memory session first, then trim it so it is never persisted.
        self._apply_temp_state(session, event)
        event = self._trim_temp_delta_state(event)
        # The mutation keys must not linger in session.state: a LATER
        # event in the SAME invocation (another tool call this turn)
        # would otherwise read them back out of state and re-apply
        # mutations that are already persisted — double application.
        session.state.pop(CASE_MUTATIONS, None)
        session.state.pop(PLAN_MUTATIONS, None)

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
        needs_user_read = bool(
            deltas["user"] or case_mutations or plan_mutations
        )

        def run_attempt(
            expected_revision: int | None,
        ) -> tuple[int, dict[str, Any], dict[str, Any]]:
            transaction = self._db.transaction()

            @firestore.transactional
            def append_txn(txn) -> tuple[int, dict[str, Any], dict[str, Any]]:
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
                    user_ref.get(transaction=txn) if needs_user_read else None
                )

                if app_snapshot is not None:
                    stored_app = app_snapshot.to_dict() or {}
                    stored_app.update(deltas["app"])
                    txn.set(app_ref, stored_app, merge=True)

                # What actually landed in adkUserState, keyed by the
                # user:-prefixed name, for reconciling session.state and
                # this event's own recorded delta below — a concurrent
                # write may have been folded into the Case/Plan here, so
                # neither may keep showing the pre-transaction value.
                final_user_delta: dict[str, Any] = {}
                if user_snapshot is not None:
                    stored_user = user_snapshot.to_dict() or {}
                    fresh_case = stored_user.get(CASE_RAW)
                    fresh_plan_state = _plan_state_from(stored_user)
                    stored_user.update(deltas["user"])
                    touched_raw_keys = set(deltas["user"].keys())
                    # The re-merged result WINS over any pre-merged blob
                    # this event's delta may also carry (a same-turn
                    # in-memory convenience write) — never trust the blob
                    # computed before this transaction re-read the
                    # freshly-stored Case/Plan. force=True whenever that
                    # blob is present, so an all-unrecognised mutation
                    # list still overrides it back to the true value
                    # rather than letting the stale blob stand.
                    if _replay_case_mutations(
                        stored_user,
                        fresh_case,
                        case_mutations,
                        force=CASE_RAW in deltas["user"],
                    ):
                        touched_raw_keys.add(CASE_RAW)
                    plan_keys_in_delta = {
                        PLAN_RAW,
                        PLAN_SEQ_IN_RAW,
                        PLAN_ACTIVE_RAW,
                    } & deltas["user"].keys()
                    if _replay_plan_mutations(
                        stored_user,
                        fresh_plan_state,
                        plan_mutations,
                        force=bool(plan_keys_in_delta),
                    ):
                        touched_raw_keys.update(
                            {PLAN_RAW, PLAN_SEQ_IN_RAW, PLAN_ACTIVE_RAW}
                        )
                    txn.set(user_ref, stored_user, merge=True)
                    for raw_key, prefixed_key in _MUTATION_RAW_TO_PREFIXED:
                        if raw_key in touched_raw_keys:
                            final_user_delta[prefixed_key] = stored_user.get(
                                raw_key
                            )

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
                # The event's own recorded delta is reconciled to what
                # was ACTUALLY persisted too — a pre-merged Case/Plan
                # blob it carried must not survive in the stored history
                # as if it were the truth. This also covers a
                # mutation-only event (e.g. the EMERGENCY button's
                # hand-built Event), whose delta is otherwise EMPTY once
                # the temp: mutation key is trimmed.
                if final_user_delta:
                    if event.actions is None:
                        event.actions = EventActions()
                    if event.actions.state_delta is None:
                        event.actions.state_delta = {}
                    event.actions.state_delta.update(final_user_delta)
                event_payload = {
                    "timestamp": event.timestamp,
                    "event": event.model_dump(mode="json", by_alias=True),
                }
                txn.set(event_ref, event_payload)
                return current_revision + 1, stored_state, final_user_delta

            return append_txn(transaction)

        marker = session._storage_update_marker
        expected = int(marker) if marker is not None else None
        try:
            new_revision, stored_state, final_user_delta = await asyncio.to_thread(
                run_attempt, expected
            )
        except StaleSessionError:
            # A concurrent turn advanced the session. Re-read storage and
            # retry once; a second loss propagates StaleSessionError so a
            # state delta is never silently dropped.
            refreshed = await asyncio.to_thread(self._read_revision, session_ref)
            new_revision, stored_state, final_user_delta = await asyncio.to_thread(
                run_attempt, refreshed
            )
            # Surface the concurrent turn's writes in the in-memory session.
            session.state.update(stored_state)

        # Reconcile the in-memory session to whatever the transaction
        # actually persisted for the Case/Plan — never the pre-merge
        # blob a caller may have also set for same-turn convenience.
        session.state.update(final_user_delta)

        await self._touch_retention(session.user_id, event.timestamp)
        await super().append_event(session, event)
        session.last_update_time = event.timestamp
        session._storage_update_marker = str(new_revision)
        return event
