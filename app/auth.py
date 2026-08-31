"""Bearer-token authentication.

The verifier is injected at app creation so tests can swap in a fake
(PRD: fake injected at the boundary; behavioral tests never mock internals).
"""

from typing import Protocol

from fastapi import HTTPException, Request

_BEARER_PREFIX = "bearer "


class TokenVerifier(Protocol):
    def verify(self, token: str) -> str:
        """Return the uid for a valid token; raise HTTPException(401) otherwise."""
        ...


class FirebaseTokenVerifier:
    """Verifies Firebase Authentication ID tokens via the Admin SDK."""

    def verify(self, token: str) -> str:
        from firebase_admin import auth as fb_auth

        try:
            decoded = fb_auth.verify_id_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return decoded["uid"]


def get_current_uid(request: Request) -> str:
    """FastAPI dependency: extract and verify the Bearer token, return uid."""
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith(_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = header[len(_BEARER_PREFIX):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    verifier: TokenVerifier = request.app.state.verifier
    return verifier.verify(token)
