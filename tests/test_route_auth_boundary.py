"""Route audit (issue #49): every route the deployed service exposes must
require a verified Firebase ID token before it can do anything, EXCEPT a
short, explicitly justified allowlist below. This walks the live FastAPI
app's route table structurally, so a future route that forgets
``Depends(get_current_uid)`` fails this test instead of shipping to the
public, IAM-unauthenticated Cloud Run URL a judge hits directly.

Verified empirically (see git history) that FastAPI resolves
``Depends(get_current_uid)`` before body validation for every route below:
an unauthenticated request with an empty/invalid JSON body still gets 401,
never a 422 that would mask the missing auth check. So every POST route is
exercised with ``json={}`` and no Authorization header.
"""

from fastapi.testclient import TestClient

from app.main import create_app

# Routes reachable with NO Firebase ID token, and exactly why each is safe:
#
# - GET "/" and the "/static" mount: the static bundle itself (HTML/JS/CSS).
#   It must load before Firebase Auth can even initialize.
# - GET /api/health: liveness probe (Cloud Run + the deploy workflow's
#   post-deploy curl check hit it with no credentials by design).
# - GET /api/firebase-config: the Firebase Web SDK config (apiKey,
#   authDomain, etc.). These values are public-by-design per Firebase's own
#   docs — they identify the project, they do not authorize anything — and
#   the frontend fetches them BEFORE initializing Firebase Auth
#   (static/app.js), so gating this behind a Firebase ID token would be a
#   chicken-and-egg deadlock, not a security boundary.
_PUBLIC_GET_PATHS = {"/", "/api/health", "/api/firebase-config"}

# POST /api/internal/retention-sweep is reachable with no Firebase ID
# token, by design: it is Cloud Scheduler's server-to-server call, gated
# instead by a distinct shared-secret header it must fail-closed on
# (RETENTION_SWEEP_TOKEN, checked with hmac.compare_digest in app/main.py).
# It never calls Gemini and never returns another user's data, but it is a
# DIFFERENT auth mechanism than the rest of this audit, so it is called out
# by name rather than silently allowed like the routes above.
_INTERNAL_SHARED_SECRET_PATH = "/api/internal/retention-sweep"


def _client() -> TestClient:
    # No token verifier call is expected during this audit: every request
    # below is unauthenticated, so a verifier that raises on any call would
    # still pass — it proves auth is checked before anything else runs.
    class _UnusedVerifier:
        def verify(self, token: str) -> str:  # pragma: no cover - guard
            raise AssertionError(
                "route audit sent no token; verifier must never be called"
            )

    return TestClient(create_app(verifier=_UnusedVerifier()))


def test_static_bundle_and_health_and_firebase_config_are_public():
    client = _client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/firebase-config").status_code in (200, 503)
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_retention_sweep_rejects_no_shared_secret():
    client = _client()
    r = client.post(_INTERNAL_SHARED_SECRET_PATH)
    # Never 200 without the shared secret: 503 (sweep not configured in
    # this test app) or 403 (wrong/missing token) are both "not reachable".
    assert r.status_code in (403, 503)


def test_every_other_route_requires_a_verified_token():
    """The structural walk: anything not explicitly allowlisted above must
    401 with zero credentials. New routes are covered automatically —
    nothing needs updating here when one is added, unless it belongs on
    one of the two allowlists above (and if so, the addition should read
    like the justifications above, not a bare path string)."""
    app = create_app(verifier=object())
    client = TestClient(app)

    audited = 0
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path is None or path in _PUBLIC_GET_PATHS:
            continue
        if path == _INTERNAL_SHARED_SECRET_PATH:
            continue
        for method in methods:
            if method == "HEAD":
                continue
            audited += 1
            if method == "GET":
                response = client.get(path)
            else:
                response = client.request(method, path, json={})
            assert response.status_code == 401, (
                f"{method} {path} returned {response.status_code} with no "
                "Authorization header; every non-allowlisted route must "
                "401 before doing anything, including a Gemini call"
            )

    # A regression guard on the guard itself: if this drops to 0 the loop
    # above silently audited nothing (e.g. every route got allowlisted by
    # mistake), which would make this whole test a false positive.
    assert audited >= 10
