"""The single deletion path for a user's data (ADR-0007).

Exactly one routine — ``delete_user_subtree`` — removes a user's data,
whether the trigger is ``panic_wipe`` (her authenticated tap) or silent
retention expiry (the scheduled sweep). The two triggers differ only by
the reason code they record; a second deletion routine would eventually
miss the transcript.

Deletion is recursive because Firestore deletes never cascade: removing
``users/{uid}`` alone would orphan every session, event, and state
document underneath it. The walk uses ``list_documents`` (not ``stream``)
so documents that exist only as parents of subcollections — "missing"
documents — are found and their children deleted too.

``panic_wipe`` is a nonce-gated backend HTTP endpoint and must NEVER be
registered as an agent tool (see tests/test_agent_tool_guard.py).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

logger = logging.getLogger(__name__)


class DeletionReason(str, Enum):
    """Why the subtree was deleted. The only difference between the paths."""

    PANIC_WIPE = "panic_wipe"
    RETENTION_EXPIRY = "retention_expiry"


@dataclass(frozen=True)
class DeletionResult:
    uid: str
    reason: DeletionReason
    documents_deleted: int


def delete_document_tree(doc_ref) -> int:
    """Deletes a document and everything below it; returns delete count."""
    deleted = 0
    for collection in doc_ref.collections():
        # list_documents surfaces missing parent documents whose
        # subcollections still hold data; stream() would skip them.
        for child in collection.list_documents():
            deleted += delete_document_tree(child)
    doc_ref.delete()
    return deleted + 1


def delete_user_subtree(db, uid: str, *, reason: DeletionReason) -> DeletionResult:
    """Recursively deletes users/{uid} and every document beneath it.

    This is the ONLY code path that deletes user data. Both panic_wipe
    and retention expiry call it; they differ only in ``reason``.
    Expiry is silent by design — nothing here notifies anyone.
    """
    user_ref = db.collection("users").document(uid)
    deleted = delete_document_tree(user_ref)
    result = DeletionResult(uid=uid, reason=reason, documents_deleted=deleted)
    # Reason code recorded (structured log line, never a notification).
    logger.info(
        "user subtree deleted",
        extra={"reason": reason.value, "documents_deleted": deleted},
    )
    return result


class UserDataDeleter(Protocol):
    """HTTP-seam dependency so tests can inject a fake at the boundary."""

    def wipe(self, uid: str, *, reason: DeletionReason) -> DeletionResult: ...


class FirestoreUserDataDeleter:
    def __init__(self, db) -> None:
        self._db = db

    def wipe(self, uid: str, *, reason: DeletionReason) -> DeletionResult:
        return delete_user_subtree(self._db, uid, reason=reason)


_deleter: UserDataDeleter | None = None


def get_user_deleter() -> UserDataDeleter:
    """FastAPI dependency; production wiring uses the Firestore client."""
    global _deleter
    if _deleter is None:
        from google.cloud import firestore

        _deleter = FirestoreUserDataDeleter(firestore.Client())
    return _deleter
