"""Gabay OFW FastAPI application."""

import json
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import FirebaseTokenVerifier, TokenVerifier, get_current_uid
from app.config import get_firebase_web_config, get_gemini_api_key
from app.contract_check import (
    ContractCheckMessage,
    ContractCheckModelOutputError,
    ContractCheckNotFoundError,
    ContractCheckNotResumableError,
    ContractCheckPersistenceError,
    ContractCheckProviderError,
    ContractCheckResponse,
    ContractCheckService,
    ContractCheckStart,
)
from app.firestore_session_service import FirestoreSessionService
from app.notes import NotesStore, get_notes_store

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_LOGGER = logging.getLogger(__name__)


def _contract_check_http_error(error: Exception) -> HTTPException:
    request_id = uuid4().hex
    diagnostic: dict[str, object] = {
        "event": "contract_check_failed",
        "request_id": request_id,
    }
    if isinstance(error, ContractCheckModelOutputError):
        diagnostic.update(category="model_output", issues=error.issues)
        status_code = 502
        message = "Gemini returned an invalid response"
    elif isinstance(error, ContractCheckProviderError):
        diagnostic.update(
            category="model_provider",
            provider_status=error.status_code,
            provider_reason=error.reason,
        )
        status_code = 503
        # A 429 (RESOURCE_EXHAUSTED) or 5xx is a genuine transient failure
        # worth retrying. Any other 4xx (INVALID_ARGUMENT for a bad/expired
        # API key, PERMISSION_DENIED, UNAUTHENTICATED, NOT_FOUND for an
        # unavailable model, etc.) will not be fixed by retrying.
        is_transient = error.status_code == 429 or error.status_code >= 500
        if is_transient:
            message = "Gemini is temporarily unavailable"
        else:
            message = "Gemini is not configured correctly. Please contact support"
    elif isinstance(error, ContractCheckPersistenceError):
        diagnostic["category"] = "persistence"
        status_code = 503
        message = "Contract Check storage is temporarily unavailable"
    else:
        raise TypeError(f"Unsupported Contract Check error: {type(error).__name__}")
    _LOGGER.warning(json.dumps(diagnostic, separators=(",", ":")))
    return HTTPException(
        status_code=status_code,
        detail=f"{message}. Reference: {request_id}",
        headers={"X-Request-ID": request_id},
    )


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def create_app(
    verifier: TokenVerifier | None = None,
    contract_checks: ContractCheckService | None = None,
) -> FastAPI:
    app = FastAPI(title="Gabay OFW", docs_url=None, redoc_url=None)
    app.state.verifier = verifier or FirebaseTokenVerifier()
    app.state.contract_checks = contract_checks

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
    def diag(uid: str = Depends(get_current_uid)):
        # Never exposes the key itself — presence only.
        return {"uid": uid, "gemini_key_loaded": get_gemini_api_key() is not None}

    @app.post("/api/notes", status_code=201)
    def create_note(
        note: NoteIn,
        uid: str = Depends(get_current_uid),
        store: NotesStore = Depends(get_notes_store),
    ):
        return {"id": store.put_note(uid, note.text)}

    @app.get("/api/notes")
    def list_notes(
        uid: str = Depends(get_current_uid),
        store: NotesStore = Depends(get_notes_store),
    ):
        return {"notes": store.get_notes(uid)}

    @app.post(
        "/api/contract-checks",
        status_code=201,
        response_model=ContractCheckResponse,
    )
    async def start_contract_check(
        request: ContractCheckStart,
        uid: str = Depends(get_current_uid),
    ):
        service: ContractCheckService | None = app.state.contract_checks
        if service is None:
            raise HTTPException(
                status_code=503, detail="Contract Check service is not configured"
            )
        try:
            return await service.start(uid, request.message)
        except (
            ContractCheckModelOutputError,
            ContractCheckProviderError,
            ContractCheckPersistenceError,
        ) as error:
            raise _contract_check_http_error(error)

    @app.post(
        "/api/contract-checks/{check_id}/messages",
        response_model=ContractCheckResponse,
    )
    async def resume_contract_check(
        check_id: str,
        request: ContractCheckMessage,
        uid: str = Depends(get_current_uid),
    ):
        service: ContractCheckService | None = app.state.contract_checks
        if service is None:
            raise HTTPException(
                status_code=503, detail="Contract Check service is not configured"
            )
        try:
            return await service.resume(
                uid, check_id, request.interrupt_id, request.message
            )
        except ContractCheckNotFoundError:
            raise HTTPException(status_code=404, detail="Contract Check not found")
        except ContractCheckNotResumableError:
            raise HTTPException(
                status_code=409, detail="Contract Check cannot be resumed"
            )
        except (
            ContractCheckModelOutputError,
            ContractCheckProviderError,
            ContractCheckPersistenceError,
        ) as error:
            raise _contract_check_http_error(error)

    if _STATIC_DIR.is_dir():

        @app.get("/")
        def index():
            return FileResponse(_STATIC_DIR / "index.html")

        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


def production_app() -> FastAPI:
    import firebase_admin
    from google.adk.models.google_llm import Gemini
    from google.cloud import firestore
    from google.genai import Client

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("Gemini API key is not configured")
    model_client = Client(api_key=api_key)
    # gemini-2.5-flash is being phased out ahead of its Oct 2026 retirement
    # date and was intermittently rejected with 404s in production; use the
    # current agentic-workload Flash model instead.
    model = Gemini(model="gemini-3.5-flash", client=model_client)
    service = ContractCheckService(
        session_service=FirestoreSessionService(firestore.Client()),
        interviewer_model=model,
        rule_matcher_model=model,
    )
    return create_app(contract_checks=service)
