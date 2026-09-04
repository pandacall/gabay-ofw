"""DISPATCHER thinks before it routes (issue #76, parent #69).

Two guarantees, verified two ways:

* Structural — the built-in planner sits on DISPATCHER at thinking level
  MEDIUM with thought summaries off, sits on NO other agent in the tree,
  and NO agent anywhere sets a token-based thinking budget. This mirrors
  the existing live-tree scans (test_agent_tool_guard, test_dev_ui_absent):
  a later refactor cannot quietly spread the planner or reintroduce a
  budget without turning this red.
* Behavioural — a model response carrying a thought part never contributes
  that text to her reply, and that holds even when thought summaries are
  enabled (test_thought_part_filter.py drives the model boundary).
"""

from google.adk.models import BaseLlm, LlmResponse
from google.adk.planners import BuiltInPlanner
from google.genai import types

from app.agent import (
    DISPATCHER_THINKING_LEVEL,
    build_adk_app,
    build_dispatcher_planner,
)


class _NeverCalledLlm(BaseLlm):
    model: str = "structural-test-only"

    async def generate_content_async(self, llm_request, stream: bool = False):
        raise AssertionError("structural test must never run a model")
        yield LlmResponse(content=types.Content(role="model", parts=[]))


def _walk_agents(root):
    stack = [root]
    while stack:
        agent = stack.pop()
        yield agent
        stack.extend(getattr(agent, "sub_agents", None) or [])


def _tree():
    return build_adk_app(_NeverCalledLlm()).root_agent


def test_dispatcher_carries_the_builtin_planner_at_medium_summaries_off():
    dispatcher = _tree()
    assert dispatcher.name == "DISPATCHER"
    planner = dispatcher.planner
    assert isinstance(planner, BuiltInPlanner)
    assert planner.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM
    assert planner.thinking_config.thinking_level == DISPATCHER_THINKING_LEVEL
    assert not planner.thinking_config.include_thoughts


def test_no_specialist_or_emergency_agent_carries_a_planner():
    for agent in _walk_agents(_tree()):
        if agent.name == "DISPATCHER":
            continue
        assert getattr(agent, "planner", None) is None, (
            f"agent {agent.name!r} carries a planner; only DISPATCHER may "
            "(issue #76 — a planner fights a specialist's output schema, and "
            "EMERGENCY's safety artifact is the zero-model hotline card)"
        )


def test_a_token_thinking_budget_is_never_set_anywhere_in_the_tree():
    for agent in _walk_agents(_tree()):
        planner = getattr(agent, "planner", None)
        if planner is None:
            continue
        thinking_config = getattr(planner, "thinking_config", None)
        if thinking_config is None:
            continue
        assert thinking_config.thinking_budget is None, (
            f"agent {agent.name!r} sets thinking_budget="
            f"{thinking_config.thinking_budget!r}; issue #76 forbids a "
            "token budget (rejected by the SDK against the pinned model — a "
            "level is the only supported knob)"
        )


def test_build_dispatcher_planner_sets_no_budget():
    planner = build_dispatcher_planner()
    assert planner.thinking_config.thinking_budget is None
    assert planner.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM
    assert not planner.thinking_config.include_thoughts
