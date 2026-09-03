"""Single-use nonces gating destructive endpoints (panic_wipe, mark_safe).

The nonce forces a deliberate two-step from the authenticated UI (fetch a
nonce, then act with it), so a replayed request, a prefetch, or a script
can never trigger the action with a bearer token alone. Nonces are held
in process memory only — never in Firestore, where the wipe itself would
race them — and are single-use with a short expiry.
"""

from __future__ import annotations

import hmac
import secrets
import time
from typing import Protocol

NONCE_TTL_SECONDS = 300.0


class NonceStore(Protocol):
    def issue(self, uid: str, action: str) -> str: ...

    def consume(self, uid: str, action: str, nonce: str) -> bool:
        """True exactly once for a live nonce issued to this uid+action."""
        ...


class InMemoryNonceStore:
    def __init__(
        self, ttl_seconds: float = NONCE_TTL_SECONDS, clock=time.monotonic
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._live: dict[tuple[str, str], tuple[str, float]] = {}

    def issue(self, uid: str, action: str) -> str:
        nonce = secrets.token_urlsafe(32)
        # One live nonce per uid+action; reissuing invalidates the old one.
        self._live[(uid, action)] = (nonce, self._clock() + self._ttl)
        return nonce

    def consume(self, uid: str, action: str, nonce: str) -> bool:
        entry = self._live.pop((uid, action), None)
        if entry is None:
            return False
        expected, expires_at = entry
        if self._clock() > expires_at:
            return False
        return hmac.compare_digest(expected, nonce)


_store: NonceStore | None = None


def get_nonce_store() -> NonceStore:
    """FastAPI dependency. In-memory is correct for the single-instance
    deployment (min-instances=1); nonces must never touch Firestore."""
    global _store
    if _store is None:
        _store = InMemoryNonceStore()
    return _store
