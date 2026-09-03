"""Pure retention tests (ADR-0007, issue #40).

The invariant under test: the deadline component of expiry is absolute —
it does not shrink with inactivity. A detained user must not lose her
evidence because she stopped opening the app. Plus the shared-path
assertions: wipe and expiry route through the one deletion routine,
differing only by reason code.
"""

from datetime import datetime, timedelta, timezone

from app import deletion, retention
from app.deletion import (
    DeletionReason,
    DeletionResult,
    FirestoreUserDataDeleter,
)
from app.retention import (
    BASE_WINDOW,
    DEADLINE_MARGIN,
    compute_expire_at,
    sweep_expired,
)

T0 = datetime(2026, 9, 3, tzinfo=timezone.utc)


class TestComputeExpireAt:
    def test_no_deadlines_expires_after_the_inactivity_window(self):
        assert compute_expire_at(T0) == T0 + BASE_WINDOW

    def test_deadline_component_dominates_inactivity(self):
        # Long-inactive user (activity far in the past) with a live claim
        # deadline a year out: the deadline component wins outright.
        stale_activity = T0 - timedelta(days=400)
        deadline = T0 + timedelta(days=365)
        expire_at = compute_expire_at(stale_activity, [deadline])
        assert expire_at == deadline + DEADLINE_MARGIN
        assert expire_at > stale_activity + BASE_WINDOW

    def test_deadline_component_is_absolute_under_growing_inactivity(self):
        # More inactivity never pulls expiry below the deadline component.
        deadline = T0 + timedelta(days=365)
        recent = compute_expire_at(T0, [deadline])
        long_detained = compute_expire_at(T0 - timedelta(days=300), [deadline])
        assert long_detained == recent == deadline + DEADLINE_MARGIN

    def test_window_never_undercuts_a_live_deadline(self):
        # Even when the inactivity window is the larger component, the
        # result always covers every live deadline.
        near_deadline = T0 + timedelta(days=7)
        expire_at = compute_expire_at(T0, [near_deadline])
        assert expire_at >= near_deadline
        assert expire_at == T0 + BASE_WINDOW

    def test_latest_live_deadline_wins(self):
        deadlines = [
            T0 + timedelta(days=30),
            T0 + timedelta(days=365),
            T0 + timedelta(days=90),
        ]
        assert (
            compute_expire_at(T0 - timedelta(days=200), deadlines)
            == T0 + timedelta(days=365) + DEADLINE_MARGIN
        )

    def test_windows_are_tunable(self):
        expire_at = compute_expire_at(
            T0,
            [T0 + timedelta(days=10)],
            base_window=timedelta(days=1),
            deadline_margin=timedelta(days=2),
        )
        assert expire_at == T0 + timedelta(days=12)


class _StubQuery:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def stream(self):
        return iter(self._snapshots)


class _StubSnapshot:
    def __init__(self, uid):
        self.id = uid


class _StubUsersCollection:
    def __init__(self, expired_uids):
        self._expired = expired_uids

    def where(self, *args, **kwargs):
        return _StubQuery([_StubSnapshot(uid) for uid in self._expired])


class _StubDb:
    def __init__(self, expired_uids):
        self._expired = expired_uids

    def collection(self, name):
        assert name == "users"
        return _StubUsersCollection(self._expired)


class TestSingleDeletionPath:
    """Wipe and expiry share exactly one deletion routine (ADR-0007)."""

    def test_expiry_and_wipe_reference_the_same_routine(self):
        assert retention.delete_user_subtree is deletion.delete_user_subtree

    def test_sweep_routes_every_expired_user_through_the_single_path(
        self, monkeypatch
    ):
        calls = []

        def record(db, uid, *, reason):
            calls.append((uid, reason))
            return DeletionResult(uid=uid, reason=reason, documents_deleted=1)

        monkeypatch.setattr(retention, "delete_user_subtree", record)
        results = sweep_expired(_StubDb(["expired-1", "expired-2"]), now=T0)
        assert calls == [
            ("expired-1", DeletionReason.RETENTION_EXPIRY),
            ("expired-2", DeletionReason.RETENTION_EXPIRY),
        ]
        assert [r.reason for r in results] == [DeletionReason.RETENTION_EXPIRY] * 2

    def test_wipe_routes_through_the_single_path_with_its_reason_code(
        self, monkeypatch
    ):
        calls = []

        def record(db, uid, *, reason):
            calls.append((uid, reason))
            return DeletionResult(uid=uid, reason=reason, documents_deleted=1)

        monkeypatch.setattr(deletion, "delete_user_subtree", record)
        FirestoreUserDataDeleter(db=None).wipe(
            "alice", reason=DeletionReason.PANIC_WIPE
        )
        assert calls == [("alice", DeletionReason.PANIC_WIPE)]
