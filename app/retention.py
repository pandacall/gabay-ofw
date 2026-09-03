"""Retention expiry (ADR-0007): deadline-aware, silent, single deletion path.

    expireAt = max(last_activity + BASE_WINDOW,
                   latest_live_deadline + DEADLINE_MARGIN)

The deadline component is absolute — it does not shrink with inactivity.
A detained user, or one whose phone was taken for months, must not lose
her evidence before her claim deadlines pass (Qatar's claim window is a
year). Native Firestore TTL cannot express this and does not cascade to
subcollections, so expiry is a scheduled sweep that reuses the single
recursive deletion path with the ``retention_expiry`` reason code.

Expiry is silent by design: no notification is ever sent (a notification
about an abusive-employer case is itself a safety incident).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from google.cloud import firestore

from app.deletion import DeletionReason, DeletionResult, delete_user_subtree

# Tunable retention constants (ADR-0007). The base window covers ordinary
# inactivity; the margin keeps a case past its latest live deadline.
BASE_WINDOW = timedelta(days=180)
DEADLINE_MARGIN = timedelta(days=90)

_EXPIRE_AT_FIELD = "expireAt"


def compute_expire_at(
    last_activity: datetime,
    live_deadlines: Iterable[datetime] = (),
    *,
    base_window: timedelta = BASE_WINDOW,
    deadline_margin: timedelta = DEADLINE_MARGIN,
) -> datetime:
    """Pure expiry computation. The deadline component dominates inactivity:
    the retention window never undercuts a live Plan deadline."""
    expire_at = last_activity + base_window
    deadlines = list(live_deadlines)
    if deadlines:
        expire_at = max(expire_at, max(deadlines) + deadline_margin)
    return expire_at


def touch_expire_at(
    db,
    uid: str,
    *,
    last_activity: datetime,
    live_deadlines: Iterable[datetime] = (),
) -> datetime:
    """Recomputes and stores users/{uid}.expireAt, monotonically.

    The stored value only ever moves later: a touch that knows fewer
    deadlines than an earlier one (e.g. a plain conversation turn versus a
    Plan publish) must not shrink the deadline-backed retention promise.
    """
    computed = compute_expire_at(last_activity, live_deadlines)
    user_ref = db.collection("users").document(uid)
    transaction = db.transaction()

    @firestore.transactional
    def touch_txn(txn) -> datetime:
        snapshot = user_ref.get(transaction=txn)
        stored = (snapshot.to_dict() or {}).get(_EXPIRE_AT_FIELD)
        new_value = max(computed, stored) if stored is not None else computed
        txn.set(user_ref, {_EXPIRE_AT_FIELD: new_value}, merge=True)
        return new_value

    return touch_txn(transaction)


def sweep_expired(db, *, now: datetime) -> list[DeletionResult]:
    """Scheduled recursive delete of every expired user subtree.

    Uses the same deletion routine as panic_wipe (ADR-0007: exactly one
    deletion path), differing only by reason code. Silent: no notification.
    """
    expired = (
        db.collection("users")
        .where(filter=firestore.FieldFilter(_EXPIRE_AT_FIELD, "<=", now))
        .stream()
    )
    return [
        delete_user_subtree(db, snapshot.id, reason=DeletionReason.RETENTION_EXPIRY)
        for snapshot in expired
    ]


class RetentionSweeper:
    """HTTP-seam dependency for the scheduled sweep endpoint.

    The Firestore client is created lazily on the first ``sweep`` call, not
    at dependency-resolution time: FastAPI resolves ``Depends`` before the
    handler's shared-secret check runs, so constructing a client here would
    make an unauthenticated request require credentials (and fail closed as
    a 500 on hosts without ADC) before the 403/503 is ever reached.
    """

    def __init__(self, db=None) -> None:
        self._db = db

    def sweep(self, *, now: datetime) -> list[DeletionResult]:
        if self._db is None:
            self._db = firestore.Client()
        return sweep_expired(self._db, now=now)


_sweeper: RetentionSweeper | None = None


def get_retention_sweeper() -> RetentionSweeper:
    global _sweeper
    if _sweeper is None:
        _sweeper = RetentionSweeper()
    return _sweeper
