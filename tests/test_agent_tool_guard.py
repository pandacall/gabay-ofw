"""Structural guard (issue #40): panic_wipe and mark_safe are nonce-gated
backend HTTP endpoints and must be unreachable as agent tools.

The scan imports every module in the ``app`` package and inspects every
ADK agent it defines. It is intentionally vacuous until agents land —
from that moment on, any agent registering a tool with a forbidden name
fails this test.
"""

import importlib
import pkgutil

import app as app_package
from app.main import create_app

FORBIDDEN_TOOL_NAMES = {"panic_wipe", "mark_safe"}


def _app_modules():
    yield app_package
    for info in pkgutil.walk_packages(app_package.__path__, "app."):
        yield importlib.import_module(info.name)


def _tool_names(agent) -> set[str]:
    names = set()
    for tool in getattr(agent, "tools", None) or []:
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        if isinstance(name, str):
            names.add(name)
    return names


def test_no_agent_in_the_app_package_registers_wipe_or_mark_safe():
    from google.adk.agents import BaseAgent

    for module in _app_modules():
        for value in vars(module).values():
            if isinstance(value, BaseAgent):
                overlap = _tool_names(value) & FORBIDDEN_TOOL_NAMES
                assert not overlap, (
                    f"{module.__name__} exposes {overlap} as agent tools; "
                    "panic_wipe and mark_safe are backend endpoints only"
                )


def test_the_built_agent_tree_never_reaches_wipe_or_mark_safe():
    """Walks the real ADK App's agent tree (DISPATCHER and any sub-agents,
    present or future) and asserts no tool with a forbidden name anywhere."""
    from google.adk.models import BaseLlm, LlmResponse
    from google.genai import types

    from app.agent import build_adk_app

    class _NeverCalledLlm(BaseLlm):
        model: str = "structural-test-only"

        async def generate_content_async(self, llm_request, stream: bool = False):
            raise AssertionError("structural test must never run a model")
            yield LlmResponse(content=types.Content(role="model", parts=[]))

    adk_app = build_adk_app(_NeverCalledLlm())
    stack = [adk_app.root_agent]
    seen = 0
    while stack:
        agent = stack.pop()
        seen += 1
        overlap = _tool_names(agent) & FORBIDDEN_TOOL_NAMES
        assert not overlap, (
            f"agent {agent.name!r} exposes {overlap}; panic_wipe and "
            "mark_safe are nonce-gated backend endpoints, never tools"
        )
        stack.extend(getattr(agent, "sub_agents", None) or [])
    assert seen >= 1


def test_wipe_and_mark_safe_are_exposed_only_as_nonce_gated_http_routes():
    app = create_app(verifier=object())
    paths = {route.path for route in app.routes}
    assert "/api/panic-wipe" in paths
    assert "/api/panic-wipe/nonce" in paths
    assert "/api/mark-safe" in paths
    assert "/api/mark-safe/nonce" in paths


def test_deletion_and_retention_modules_never_touch_the_agent_layer():
    # The single deletion path must not be importable as a tool from its
    # own modules: neither module may depend on google.adk.
    import app.deletion
    import app.retention
    import inspect

    for module in (app.deletion, app.retention):
        assert "google.adk" not in inspect.getsource(module)
