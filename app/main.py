"""Gabay OFW FastAPI application."""

import hmac
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import FirebaseTokenVerifier, TokenVerifier, get_current_uid
from app.chat import ChatService, stream_stateless_fallback
from app.config import (
    get_firebase_web_config,
    get_gemini_api_key,
    get_retention_sweep_token,
)
from app.deletion import DeletionReason, UserDataDeleter, get_user_deleter
from app.nonces import NonceStore, get_nonce_store
from app.notes import NotesStore, get_notes_store
from app.retention import RetentionSweeper, get_retention_sweeper

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# panic_wipe and mark_safe are nonce-gated backend HTTP endpoints, NEVER
# agent tools; no agent may reach them (guard: tests/test_agent_tool_guard.py).
_WIPE_ACTION = "panic_wipe"
_MARK_SAFE_ACTION = "mark_safe"


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ChatTurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class NonceIn(BaseModel):
    nonce: str = Field(min_length=1, max_length=200)


def _production_chat_service() -> ChatService:
    """Built lazily on the first chat request so tests and health checks
    never touch Firestore or the Gemini key."""
    from google import genai
    from google.adk.models import Gemini
    from google.cloud import firestore

    from app.agent import GEMINI_MODEL
    from app.firestore_session_service import FirestoreSessionService

    api_key = get_gemini_api_key()
    if api_key is None:
        raise HTTPException(status_code=503, detail="Gemini API key not available")
    return ChatService(
        session_service=FirestoreSessionService(firestore.Client()),
        llm=Gemini(model=GEMINI_MODEL, client=genai.Client(api_key=api_key)),
    )


def get_chat_service(request: Request) -> ChatService:
    service = request.app.state.chat_service
    if service is None:
        service = _production_chat_service()
        request.app.state.chat_service = service
    return service


def create_app(
    verifier: TokenVerifier | None = None,
    chat_service: ChatService | None = None,
) -> FastAPI:
    app = FastAPI(title="Gabay OFW", docs_url=None, redoc_url=None)
    app.state.verifier = verifier or FirebaseTokenVerifier()
    app.state.chat_service = chat_service

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/firebase-config")
    def firebase_config():
        config = get_firebase_web_config()
        if config is None:
            raise HTTPException(status_code=503, detail="Firebase web config not set")
        return config

    @app.get("/api/diag")
    async def diag(uid: str = Depends(get_current_uid)):
        # Never exposes the key itself — presence only.
        result: dict[str, object] = {
            "uid": uid,
            "gemini_key_loaded": get_gemini_api_key() is not None,
        }
        return result

    @app.post("/api/notes", status_code=201)
    def create_note(
        note: NoteIn,
        uid: str = Depends(get_current_uid),
        store: NotesStore = Depends(get_notes_store),
    ):
        return {"id": store.put_note(uid, note.text)}

    @app.post("/api/chat")
    async def chat_turn(
        turn: ChatTurnIn,
        uid: str = Depends(get_current_uid),
        service: ChatService = Depends(get_chat_service),
    ):
        try:
            session = await service.get_or_create_session(
                uid=uid, session_id=turn.session_id
            )
        except Exception:
            # Session store down: the hard fallback — the cached Safe
            # Floor card with zero model calls, surfaced not swallowed.
            logging.getLogger(__name__).exception("session store unavailable")
            return StreamingResponse(
                stream_stateless_fallback(),
                media_type="application/x-ndjson",
            )
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return StreamingResponse(
            service.stream_turn(uid=uid, session=session, text=turn.text),
            media_type="application/x-ndjson",
        )

    @app.get("/api/notes")
    def list_notes(
        uid: str = Depends(get_current_uid),
        store: NotesStore = Depends(get_notes_store),
    ):
        return {"notes": store.get_notes(uid)}

    @app.post("/api/panic-wipe/nonce")
    def panic_wipe_nonce(
        uid: str = Depends(get_current_uid),
        nonces: NonceStore = Depends(get_nonce_store),
    ):
        return {"nonce": nonces.issue(uid, _WIPE_ACTION)}

    @app.post("/api/panic-wipe")
    def panic_wipe(
        body: NonceIn,
        uid: str = Depends(get_current_uid),
        nonces: NonceStore = Depends(get_nonce_store),
        deleter: UserDataDeleter = Depends(get_user_deleter),
    ):
        """One authenticated action deletes the user's entire subtree.

        Nonce-gated backend endpoint — never an agent tool. The deletion
        itself is the single shared path in app.deletion.
        """
        if not nonces.consume(uid, _WIPE_ACTION, body.nonce):
            raise HTTPException(status_code=403, detail="Invalid or expired nonce")
        result = deleter.wipe(uid, reason=DeletionReason.PANIC_WIPE)
        return {"wiped": True, "documents_deleted": result.documents_deleted}

    @app.post("/api/emergency/button")
    async def emergency_button(
        uid: str = Depends(get_current_uid),
        service: ChatService = Depends(get_chat_service),
    ):
        """The hardcoded EMERGENCY button (issue #41): renders the cached
        action card OFFLINE, with ZERO model turns. Not a conversation —
        a fixed, code-owned render plus a timestamped predicate trip; the
        conversational EMERGENCY sub-agent takes over from her next chat
        message once the predicate is active."""
        return StreamingResponse(
            service.press_emergency_button(uid=uid),
            media_type="application/x-ndjson",
        )

    @app.post("/api/mark-safe/nonce")
    def mark_safe_nonce(
        uid: str = Depends(get_current_uid),
        nonces: NonceStore = Depends(get_nonce_store),
    ):
        return {"nonce": nonces.issue(uid, _MARK_SAFE_ACTION)}

    @app.post("/api/mark-safe")
    async def mark_safe(
        body: NonceIn,
        uid: str = Depends(get_current_uid),
        nonces: NonceStore = Depends(get_nonce_store),
        service: ChatService = Depends(get_chat_service),
    ):
        """Clears the Imminent Danger PREDICATE — never the safety flag
        (issue #41). A coerced tap must not erase the disclosure: the
        flag and its provenance survive; only the timestamped latch
        flips off, so the app re-evaluates honestly next turn instead of
        pretending the tap never happened. Nonce-gated backend endpoint
        — never an agent tool."""
        if not nonces.consume(uid, _MARK_SAFE_ACTION, body.nonce):
            raise HTTPException(status_code=403, detail="Invalid or expired nonce")
        case = await service.apply_mark_safe(uid=uid)
        return {"marked_safe": True, "case": case}

    @app.post("/api/internal/retention-sweep")
    def retention_sweep(
        request: Request,
        sweeper: RetentionSweeper = Depends(get_retention_sweeper),
    ):
        """Scheduled recursive delete of expired subtrees (Cloud Scheduler).

        Guarded by a shared secret header, not a user token: the sweep acts
        across users. Silent by design — no notification is ever produced.
        """
        expected = get_retention_sweep_token()
        if not expected:
            raise HTTPException(status_code=503, detail="Sweep not configured")
        provided = request.headers.get("X-Retention-Sweep-Token", "")
        if not hmac.compare_digest(expected, provided):
            raise HTTPException(status_code=403, detail="Invalid sweep token")
        results = sweeper.sweep(now=datetime.now(timezone.utc))
        return {"expired_users": len(results)}

    if _STATIC_DIR.is_dir():

        @app.get("/")
        def index():
            return FileResponse(_STATIC_DIR / "index.html")

        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


def production_app() -> FastAPI:
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    return create_app()
