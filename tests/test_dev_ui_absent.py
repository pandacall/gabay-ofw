"""Dev UI absence (issue #49): google-adk ships an unauthenticated agent
console (``adk web`` / ``adk api_server``, both built on
``google.adk.cli.fast_api.get_fast_api_app`` / ``ApiServer``) intended for
local development only. Mounting or running it anywhere in the deployed
container would let anyone with the public Cloud Run URL drive every
specialist agent directly, with no Firebase ID token and no
ROUTING_GUARD — disqualifying for a demo. This is a structural scan, not a
network probe: it proves the entry points are never imported/invoked
anywhere the deployed container executes, so it fails immediately if
someone later wires the dev UI in rather than needing a live deploy to
catch it.
"""

import importlib
import pkgutil
from pathlib import Path

import app as app_package
from app.main import create_app

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Any of these appearing in code the deployed container executes means the
# dev UI (or its console-script entry points) is reachable.
_DEV_UI_MARKERS = (
    "google.adk.cli",
    "get_fast_api_app",
    "ApiServer",
    "adk web",
    "adk api_server",
    "adk_web",
)


def _app_modules():
    yield app_package
    for info in pkgutil.walk_packages(app_package.__path__, "app."):
        yield importlib.import_module(info.name)


def test_no_app_module_imports_or_names_the_dev_ui():
    import inspect

    checked = 0
    for module in _app_modules():
        if getattr(module, "__file__", None) is None:
            continue  # namespace package, no source of its own to scan
        try:
            source = inspect.getsource(module)
        except OSError:
            continue  # e.g. an empty __init__.py — nothing to scan
        checked += 1
        for marker in _DEV_UI_MARKERS:
            assert marker not in source, (
                f"{module.__name__} references {marker!r}; the ADK dev UI "
                "must never be reachable from the deployed app"
            )
    assert checked >= 10


def test_dockerfile_only_runs_uvicorn_against_the_production_app():
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "CMD" in dockerfile
    for marker in _DEV_UI_MARKERS:
        assert marker not in dockerfile, (
            f"Dockerfile references {marker!r}; only uvicorn running "
            "app.main:production_app may be the container entrypoint"
        )
    assert "uvicorn" in dockerfile
    assert "app.main:production_app" in dockerfile


def test_deploy_workflow_never_invokes_the_dev_ui():
    workflow = (
        _REPO_ROOT / ".github" / "workflows" / "deploy-cloud-run.yml"
    ).read_text(encoding="utf-8")
    for marker in _DEV_UI_MARKERS:
        assert marker not in workflow, (
            f"deploy-cloud-run.yml references {marker!r}; the deploy "
            "workflow must never start the ADK dev UI"
        )


def test_the_running_app_exposes_no_dev_ui_routes():
    """Defense in depth: even if some future refactor imported the dev UI
    module without literally naming it (defeating the source scans above),
    the actual constructed FastAPI app must not expose any of the dev UI's
    known route paths (``google.adk.cli.fast_api.get_fast_api_app``)."""
    app = create_app(verifier=object())
    paths = {getattr(route, "path", "") for route in app.routes}
    # A representative subset of google.adk.cli.api_server.ApiServer's real
    # route paths (verified against the pinned 2.8.0 wheel), not the full
    # set — enough to fail loudly if the dev UI's router is ever merged in.
    dev_ui_paths = {
        "/dev-ui",
        "/dev-ui/",
        "/list-apps",
        "/run",
        "/run_sse",
        "/apps/{app_name}/users/{user_id}/sessions/{session_id}",
        "/apps/{app_name}/users/{user_id}/sessions",
    }
    assert not (paths & dev_ui_paths)
