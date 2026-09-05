"""Gabay OFW FastAPI application."""

import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.auth import FirebaseTokenVerifier, TokenVerifier, get_current_uid
from app.chat import ChatService, stream_stateless_fallback
from app.config import (
    get_firebase_web_config,
    get_gemini_api_key,
    get_retention_sweep_token,
)
from app.deletion import DeletionReason, UserDataDeleter, get_user_deleter
from app.extraction import NarrativeClaims
from app.nonces import NonceStore, get_nonce_store
from app.notes import NotesStore, get_notes_store
from app.retention import RetentionSweeper, get_retention_sweeper

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# panic_wipe and mark_safe are nonce-gated backend HTTP endpoints, NEVER
# agent tools; no agent may reach them (guard: tests/test_agent_tool_guard.py).
_WIPE_ACTION = "panic_wipe"
_MARK_SAFE_ACTION = "mark_safe"

#: The closed set of Case claim fields a one-tap correction may write —
#: exactly the fields extraction itself may assert (NarrativeClaims),
#: so a correction can never inject an arbitrary state key.
_CORRECTABLE_FIELDS = frozenset(NarrativeClaims.model_fields)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ChatTurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ConversationRenameIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)

    @field_validator("label")
    @classmethod
    def _trimmed_nonempty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("label must not be blank")
        return trimmed


class CaseCorrectionIn(BaseModel):
    session_id: str = Field(min_length=1)
    field: str
    value: str = Field(min_length=1, max_length=2000)

    @field_validator("field")
    @classmethod
    def _known_field(cls, value: str) -> str:
        if value not in _CORRECTABLE_FIELDS:
            raise ValueError(f"Unknown Case field: {value!r}")
        return value


class NonceIn(BaseModel):
    nonce: str = Field(min_length=1, max_length=200)


class EscalateIn(BaseModel):
    source_session_id: str = Field(min_length=1)


def _production_chat_service() -> ChatService:
    """Built lazily on the first chat request so tests and health checks
    never touch Firestore or the Gemini key."""
    from google import genai
    from google.adk.models import Gemini
    from google.cloud import firestore

    from app.agent import GEMINI_MODEL
    from app.firestore_session_service import FirestoreSessionService
    from app.title import build_gemini_model_call

    api_key = get_gemini_api_key()
    if api_key is None:
        raise HTTPException(status_code=503, detail="Gemini API key not available")
    client = genai.Client(api_key=api_key)
    return ChatService(
        session_service=FirestoreSessionService(firestore.Client()),
        llm=Gemini(model=GEMINI_MODEL, client=client),
        title_model=build_gemini_model_call(client, GEMINI_MODEL),
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
    # docs_url/redoc_url/openapi_url all disabled (issue #49 route audit):
    # the interactive docs are gone already, and the raw schema at
    # /openapi.json is otherwise reachable with no Firebase ID token — it
    # leaks no user data or Gemini output, but it is unauthenticated attack
    # surface with zero demo value, so it is off too.
    app = FastAPI(
        title="Gabay OFW", docs_url=None, redoc_url=None, openapi_url=None
    )
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
        background_tasks: BackgroundTasks,
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

        # spec 2026-09-05-llm-conversation-titles: the one-time LLM
        # Conversation-title attempt only ever fires on a Conversation's
        # very first turn — decided here, before the turn runs, from
        # whether any event already exists on the session. Her reply
        # text is only known once the stream below has actually produced
        # it, so it's captured into this holder as the response streams
        # and read back by the background task, which Starlette runs
        # only after the full response has been sent — never delaying
        # her reply.
        is_first_turn = not session.events
        title_ctx: dict[str, str] = {}

        async def _stream():
            async for line in service.stream_turn(
                uid=uid, session=session, text=turn.text
            ):
                if is_first_turn:
                    try:
                        payload = json.loads(line)
                    except ValueError:
                        payload = None
                    if isinstance(payload, dict) and payload.get("type") == "reply":
                        title_ctx["reply_text"] = payload.get("text", "")
                yield line

        if is_first_turn:

            async def _generate_title():
                await service.maybe_generate_title(
                    uid=uid,
                    session_id=session.id,
                    user_text=turn.text,
                    reply_text=title_ctx.get("reply_text", ""),
                )

            background_tasks.add_task(_generate_title)

        return StreamingResponse(
            _stream(),
            media_type="application/x-ndjson",
            background=background_tasks,
        )

    @app.post("/api/case/correct")
    async def correct_case(
        body: CaseCorrectionIn,
        uid: str = Depends(get_current_uid),
        service: ChatService = Depends(get_chat_service),
    ):
        """One-tap correction (issue #44): an authenticated write of a
        single Case claim, source="user" — wins outright, sets
        user_confirmed, and resolves any Conflict a prior turn raised on
        this field, per app.case.merge_case's merge policy. Session
        lookup mirrors /api/chat's: an unknown or another user's session
        id is 404, never a leak of its existence.
        """
        updated = await service.correct_case(
            uid=uid,
            session_id=body.session_id,
            field=body.field,
            value=body.value,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"case": updated}

    @app.get("/api/conversations")
    async def list_conversations(
        uid: str = Depends(get_current_uid),
        service: ChatService = Depends(get_chat_service),
    ):
        """Her Conversations for the rail (issue #72, ADR-0008): id and
        last-activity time only, most-recent first, no per-Conversation
        state loaded."""
        return {"conversations": await service.list_conversations(uid=uid)}

    @app.get("/api/conversations/{session_id}")
    async def read_conversation(
        session_id: str,
        uid: str = Depends(get_current_uid),
        service: ChatService = Depends(get_chat_service),
    ):
        """Re-open a Conversation (issue #72): its stored transcript
        streamed back as the same NDJSON line types ``/api/chat`` emits,
        so the client replays it through the identical handler. An
        unknown or another user's session id is 404, never a leak of its
        existence (mirrors ``/api/chat``)."""
        lines = await service.load_conversation(uid=uid, session_id=session_id)
        if lines is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        async def _stream():
            for line in lines:
                yield json.dumps(line, ensure_ascii=False) + "\n"

        return StreamingResponse(_stream(), media_type="application/x-ndjson")

    @app.patch("/api/conversations/{session_id}")
    async def rename_conversation(
        session_id: str,
        body: ConversationRenameIn,
        uid: str = Depends(get_current_uid),
        service: ChatService = Depends(get_chat_service),
    ):
        """Rename one Conversation (issue #73): her own word for it wins
        over any derived label, permanently, and survives every later
        turn. 404 for an unknown or another user's id (mirrors
        ``/api/chat``)."""
        if not await service.rename_conversation(
            uid=uid, session_id=session_id, label=body.label
        ):
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"label": body.label}

    @app.delete("/api/conversations/{session_id}")
    async def delete_conversation(
        session_id: str,
        uid: str = Depends(get_current_uid),
        service: ChatService = Depends(get_chat_service),
    ):
        """Delete one Conversation's transcript and nothing else (issue
        #72, ADR-0007 amendment): her user-scoped Case and Plan survive,
        and ``delete_user_subtree`` remains the only routine that removes
        a user's data. 404 for an unknown or another user's id."""
        if not await service.delete_conversation(uid=uid, session_id=session_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"deleted": True}

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

    @app.post("/api/emergency/escalate")
    async def emergency_escalate(
        body: EscalateIn,
        uid: str = Depends(get_current_uid),
        service: ChatService = Depends(get_chat_service),
    ):
        """Confirming an Escalation Prompt (ADR-0009, issue #74): opens (or
        reopens) her one Emergency Conversation carrying an Escalation
        Handoff derived from the source Conversation's Case — never its
        transcript — and leaves the source Conversation exactly as it was.
        404 for an unknown or another user's source id (mirrors
        ``/api/chat``)."""
        result = await service.escalate_from_prompt(
            uid=uid, source_session_id=body.source_session_id
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return result

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
