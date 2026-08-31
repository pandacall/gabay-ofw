"""User-scoped notes storage under users/{uid}/notes/{noteId}.

FirestoreNotesStore is the production implementation; tests inject an
in-memory fake via the get_notes_store dependency.
"""

from typing import Protocol


class NotesStore(Protocol):
    def put_note(self, uid: str, text: str) -> str: ...

    def get_notes(self, uid: str) -> list[dict]: ...


class FirestoreNotesStore:
    def __init__(self, db):
        self._db = db

    def _collection(self, uid: str):
        return self._db.collection("users").document(uid).collection("notes")

    def put_note(self, uid: str, text: str) -> str:
        from google.cloud.firestore import SERVER_TIMESTAMP

        _, ref = self._collection(uid).add({"text": text, "createdAt": SERVER_TIMESTAMP})
        return ref.id

    def get_notes(self, uid: str) -> list[dict]:
        docs = self._collection(uid).order_by("createdAt").stream()
        return [{"id": d.id, "text": d.to_dict().get("text", "")} for d in docs]


_store: NotesStore | None = None


def get_notes_store() -> NotesStore:
    """FastAPI dependency; production wiring creates a Firestore-backed store."""
    global _store
    if _store is None:
        from google.cloud import firestore

        _store = FirestoreNotesStore(firestore.Client())
    return _store
