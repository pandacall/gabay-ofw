"""Gabay OFW FastAPI application."""

from pathlib import Path

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
    ContractCheckResponse,
    ContractCheckService,
    ContractCheckStart,
)
from app.notes import NotesStore, get_notes_store

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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
        except ContractCheckModelOutputError:
            raise HTTPException(
                status_code=502, detail="Gemini returned an invalid response"
            )

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
        except ContractCheckModelOutputError:
            raise HTTPException(
                status_code=502, detail="Gemini returned an invalid response"
            )

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
