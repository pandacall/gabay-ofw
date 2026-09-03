"""Gabay OFW FastAPI application."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import FirebaseTokenVerifier, TokenVerifier, get_current_uid
from app.config import get_firebase_web_config, get_gemini_api_key
from app.notes import NotesStore, get_notes_store

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def create_app(
    verifier: TokenVerifier | None = None,
) -> FastAPI:
    app = FastAPI(title="Gabay OFW", docs_url=None, redoc_url=None)
    app.state.verifier = verifier or FirebaseTokenVerifier()

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

    @app.get("/api/notes")
    def list_notes(
        uid: str = Depends(get_current_uid),
        store: NotesStore = Depends(get_notes_store),
    ):
        return {"notes": store.get_notes(uid)}

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
