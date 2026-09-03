"""ROUTING_GUARD and voice integrity (issue #39, PRD #34, ADR-0004).

The highest-consequence code in the system: a silent failure here routes
a Saudi assault victim to local police, where HRW documents employers
counter-filing theft and *zina* charges. ROUTING_GUARD is a
:class:`BasePlugin` on the App plus a root before-tool callback on
DISPATCHER — NOT an agent. It fails closed on an allowlist enforced on
tool RESULTS: ``office_directory`` rows carry a :class:`Channel` enum and
anything outside the permitted set is dropped, so argument spelling
cannot bypass it. Local police is refused for every jurisdiction in
scope AND for unknown ones; UNKNOWN is more restrictive than
known-dangerous, never less; the guard is never conditioned on
model-extracted safety flags.

Callback return discipline (verified against the pinned google-adk 2.8.0
wheel, ``flows/llm_flows/functions.py``): a plugin callback early-exits
on ANY non-None value, and the agent-callback loop only ``break``s on a
truthy one — so returning ``{}`` from a before-tool callback silently
skips the real tool today and silently stops breaking the loop the day a
second callback exists. NEVER return ``{}``: a refusal is a structured
non-empty dict; an allow is ``None``.

Voice integrity (after-model whitelist diff): every number and date in a
reply must be a member of the values tools returned this turn (union the
values in the user's own current message — echoing her back is not
fabrication). Membership is a SET DIFF over canonicalized tokens, not a
regex strip; a non-member is re-emitted from tool results and the miss
logged.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool, ToolContext
from google.genai import types

from app.directory import Channel, Country, resolve_case_country

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The allowlist — pure data, code-owned.
# ---------------------------------------------------------------------------

#: The only tools any agent may reach. Anything else is refused before it
#: runs (fail closed). DEBUNKER and PROOF_BUILDER are specialist
#: sub-agents auto-wrapped as tools on DISPATCHER (ADR-0004);
#: search_corpus is DEBUNKER's own deterministic classifier tool.
#: ``FILING_SEQUENCER`` (issue #42) is the single wrapped tool name
#: google-adk exposes to DISPATCHER for the whole mode='single_turn'
#: sub-agent. ROUTING_GUARD's plugin callbacks apply to EVERY tool call
#: in the tree, including calls made from inside FILING_SEQUENCER's own
#: turn — so its four internal pure-function tools are allowlisted here
#: too (their results, e.g. a HELD refusal's MWO contacts, still pass
#: through the same channel filtering below). ``transfer_to_agent`` is
#: ADK's own built-in tool that performs the one-way
#: DISPATCHER->EMERGENCY handoff (issue #41's only LLM transfer) — it
#: carries no contact data of its own, so allowlisting it does not
#: weaken ROUTING_GUARD's contact-data guarantees. ``COMPLAINT_DRAFTER``
#: (issue #46) is wired the same way as the other specialists: its four
#: internal tools (agency-license gate, safe-to-file gate, form fill,
#: red-team finalize) all cross this guard too. ``RECOURSE_ROUTER``
#: (issue #48) is wired the same way: its one internal tool
#: (``recourse_build_routes``) crosses this guard too. All of these cross
#: this guard like any other tool.
ALLOWED_TOOLS = frozenset(
    {
        "office_directory",
        "action_card",
        "safe_floor_card",
        "mark_plan_step_done",
        "DEBUNKER",
        "search_corpus",
        "PROOF_BUILDER",
        "FILING_SEQUENCER",
        "sequencer_jurisdiction_rules",
        "sequencer_sequence_actions",
        "sequencer_compute_deadlines",
        "sequencer_verify_plan",
        "transfer_to_agent",
        "COMPLAINT_DRAFTER",
        "complaint_check_agency_license",
        "complaint_check_safe_to_file",
        "complaint_prepare_form",
        "complaint_review_and_finalize",
        "RECOURSE_ROUTER",
        "recourse_build_routes",
    }
)

#: The voice agents whose replies the after-model whitelist diffs.
#: Specialists' structured outputs are schema-validated and cross the
#: after-TOOL rail instead (filtered there, and their values enter the
#: turn whitelist so the voice may repeat them); diffing their raw JSON
#: would corrupt it before output-schema validation. EMERGENCY (issue
#: #41) converses freely just like DISPATCHER — the same fabrication
#: risk applies, so its replies are diffed too, never exempted just
#: because a transfer handed her the conversation.
VOICE_AGENT_NAMES = frozenset({"DISPATCHER", "EMERGENCY"})

_GULF_PERMITTED = frozenset(
    {Channel.MWO, Channel.EMBASSY_ATN, Channel.OWWA_1348, Channel.DMW_HOTLINE}
)

#: Channels permitted per country. LOCAL_POLICE is a member of NO set —
#: refused for every jurisdiction in scope and for unknown ones. UNKNOWN
#: is a proper subset of every known country's set: uncertainty narrows
#: what the app will do, never widens it.
PERMITTED_CHANNELS: dict[Country, frozenset[Channel]] = {
    Country.SA: _GULF_PERMITTED,
    Country.QA: _GULF_PERMITTED,
    Country.KW: _GULF_PERMITTED,
    Country.AE: _GULF_PERMITTED,
    Country.UNKNOWN: frozenset({Channel.EMBASSY_ATN, Channel.OWWA_1348}),
}


def permitted_for(country: Country) -> frozenset[Channel]:
    """The permitted channel set; anything unmapped gets UNKNOWN's set."""
    return PERMITTED_CHANNELS.get(country, PERMITTED_CHANNELS[Country.UNKNOWN])


def refusal(reason: str) -> dict[str, Any]:
    """A structured, NON-EMPTY refusal dict (never ``{}`` — see module doc)."""
    return {"guard": "ROUTING_GUARD", "refused": True, "reason": reason}


# ---------------------------------------------------------------------------
# Pure enforcement core (the CI-gating suite runs against these directly).
# ---------------------------------------------------------------------------


def _row_channel(row: Any) -> Optional[Channel]:
    if not isinstance(row, dict):
        return None
    try:
        return Channel(row.get("channel"))
    except (ValueError, TypeError):
        return None


def filter_rows(
    rows: Any, country: Country
) -> tuple[list[dict[str, Any]], int]:
    """Drops every row outside the permitted channel set for ``country``.

    Fails closed: a row that is not a dict, has no channel tag, or has a
    tag outside the :class:`Channel` enum is dropped. LOCAL_POLICE is
    dropped explicitly even though no permitted set contains it.
    Returns ``(kept, dropped_count)``.
    """
    permitted = permitted_for(country)
    kept: list[dict[str, Any]] = []
    dropped = 0
    for row in rows if isinstance(rows, list) else []:
        channel = _row_channel(row)
        if channel is None or channel is Channel.LOCAL_POLICE or channel not in permitted:
            dropped += 1
            continue
        kept.append(row)
    if not isinstance(rows, list):
        dropped += 1
    return kept, dropped


def filter_tool_result(result: Any, country: Country) -> tuple[dict[str, Any], int]:
    """Enforces the allowlist on a tool RESULT, recursively.

    Every list of channel-tagged dicts anywhere in the result is
    filtered; nothing else is altered. A non-dict result is replaced by a
    refusal (fail closed). Returns ``(filtered_result, dropped_count)`` —
    the filtered result is always a non-empty dict.
    """
    if not isinstance(result, dict):
        return refusal("MALFORMED_TOOL_RESULT"), 1

    dropped_total = 0

    #: Keys whose lists are contact rows by contract: ALWAYS filtered, so
    #: an untagged (channel-less) row is dropped, never passed through.
    _ROW_KEYS = ("rows", "contacts")

    def _walk(value: Any, *, key: Optional[str] = None) -> Any:
        nonlocal dropped_total
        if isinstance(value, list):
            if key in _ROW_KEYS or any(
                isinstance(item, dict) and "channel" in item for item in value
            ):
                kept, dropped = filter_rows(value, country)
                dropped_total += dropped
                return kept
            return [_walk(item) for item in value]
        if isinstance(value, dict):
            return {k: _walk(item, key=k) for k, item in value.items()}
        return value

    filtered = {key: _walk(value, key=key) for key, value in result.items()}
    filtered["guard_dropped"] = dropped_total
    return filtered, dropped_total


# ---------------------------------------------------------------------------
# Voice integrity: the after-model whitelist diff.
# ---------------------------------------------------------------------------

#: Session-state key (``temp:`` — invocation-scoped, never persisted)
#: accumulating the display strings of values tools returned this turn.
TURN_WHITELIST_KEY = "temp:turn_value_whitelist"

# Candidate tokens: digit runs possibly joined by phone/date separators,
# optionally led by '+', plus date-shaped tokens (9/3, 09-15-2026,
# "September 15", "15 ng Setyembre"). The regexes only FIND candidates —
# the decision is set membership of the canonicalized token, not a regex
# strip.
_MONTH = (
    # NOTE: bare "may" is deliberately absent — it is the Tagalog
    # existential ("may 3 anak ako") and would false-flag everyday
    # Taglish. The Tagalog month is "Mayo"; English "May 15" falls back
    # to the bare-number rules.
    r"(?:enero|pebrero|marso|abril|mayo|hunyo|hulyo|agosto|setyembre"
    r"|oktubre|nobyembre|disyembre|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?"
    r"|apr(?:il)?|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?"
    r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_DATE = (
    rf"\d{{1,2}}[/.\-]\d{{1,2}}(?:[/.\-]\d{{2,4}})?"
    rf"|{_MONTH}\.?,?\s*\d{{1,2}}(?:\s*,?\s*\d{{4}})?"
    rf"|\d{{1,2}}\s+(?:ng\s+)?{_MONTH}(?:\s*,?\s*\d{{4}})?"
)
_NUMERIC = r"\+?\d(?:[\d\-./() ]*\d)?"
_VALUE_TOKEN = re.compile(rf"(?:{_DATE})|(?:{_NUMERIC})", re.IGNORECASE)
_DATE_ONLY = re.compile(rf"^(?:{_DATE})$", re.IGNORECASE)


def canonical(token: str) -> str:
    """Lowercased alphanumeric canonical form (digits plus month letters),
    so formatting cannot cause false passes."""
    return re.sub(r"[^0-9a-z]", "", token.lower())


def _is_candidate(token: str) -> bool:
    """Whether a matched token is subject to the whitelist.

    Date-shaped tokens always are; bare digit runs of one or two digits
    ("3 months", "1am") are conversation, not contact data, and are
    exempt.
    """
    return bool(_DATE_ONLY.match(token.strip())) or len(canonical(token)) >= 3


def value_tokens(text: str) -> list[str]:
    """Number/date candidate tokens in ``text``."""
    return [
        match.group(0).strip()
        for match in _VALUE_TOKEN.finditer(text or "")
        if _is_candidate(match.group(0))
    ]


def collect_result_values(result: Any) -> list[str]:
    """Every whitelistable value in a (filtered) tool result, as displayed."""
    found: list[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            found.extend(value_tokens(value))
        elif isinstance(value, (int, float)):
            found.extend(value_tokens(str(value)))
        elif isinstance(value, list):
            for item in value:
                _walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                _walk(item)

    _walk(result)
    seen: set[str] = set()
    unique = []
    for token in found:
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def diff_reply(
    text: str,
    allowed: set[str],
    replacements: list[str],
) -> tuple[str, list[str]]:
    """The set diff: every candidate token must be a member of ``allowed``.

    ``allowed`` holds canonicalized values (tool-returned this turn plus
    the user's own current message). A non-member is re-emitted from tool
    results: replaced with the tool-returned display values when any
    exist, removed outright otherwise (fail closed — nothing is invented
    to fill the hole). Returns ``(clean_text, misses)``.
    """
    misses: list[str] = []
    replacement = ", ".join(replacements)

    def _substitute(match: re.Match[str]) -> str:
        token = match.group(0)
        if not _is_candidate(token) or canonical(token) in allowed:
            return token
        misses.append(token.strip())
        return replacement

    clean = _VALUE_TOKEN.sub(_substitute, text or "")
    if misses:
        clean = re.sub(r"[ \t]{2,}", " ", clean)
    return clean, misses


# ---------------------------------------------------------------------------
# The plugin (App-level) and the root before-tool callback (agent-level).
# Two independent rails: either alone refuses a non-allowlisted tool.
# ---------------------------------------------------------------------------


def _state_case(state: Any) -> Optional[dict[str, Any]]:
    try:
        case = state.get("case")
    except Exception:  # fail closed on any state weirdness
        return None
    return case if isinstance(case, dict) else None


class RoutingGuardPlugin(BasePlugin):
    """ROUTING_GUARD as an App plugin: tool allowlist, result filtering,
    and the after-model whitelist diff. Not an agent; never conditioned
    on model-extracted safety flags — country only."""

    def __init__(self) -> None:
        super().__init__(name="routing_guard")

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> Optional[dict[str, Any]]:
        if tool.name not in ALLOWED_TOOLS:
            logger.warning(
                "ROUTING_GUARD refused tool %r (not allowlisted)", tool.name
            )
            return refusal("TOOL_NOT_ALLOWLISTED")
        return None  # allow — never {} (see module docstring)

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        if tool.name not in ALLOWED_TOOLS:
            return refusal("TOOL_NOT_ALLOWLISTED")
        country = resolve_case_country(_state_case(tool_context.state))
        filtered, dropped = filter_tool_result(result, country)
        if dropped:
            logger.warning(
                "ROUTING_GUARD dropped %d row(s) from %r for country %s",
                dropped,
                tool.name,
                country.value,
            )
        existing = list(tool_context.state.get(TURN_WHITELIST_KEY) or [])
        for token in collect_result_values(filtered):
            if token not in existing:
                existing.append(token)
        tool_context.state[TURN_WHITELIST_KEY] = existing
        return filtered

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> Optional[LlmResponse]:
        # Voice integrity is about the REPLY: only a voice agent's text
        # is diffed. A specialist's model output is a structured payload
        # validated by its output_schema and filtered on the after-tool
        # rail — rewriting its JSON here would corrupt it into a
        # validation failure instead of a caught fabrication.
        if callback_context.agent_name not in VOICE_AGENT_NAMES:
            return None
        content = llm_response.content
        if content is None or not content.parts:
            return None
        tool_values = list(
            callback_context.state.get(TURN_WHITELIST_KEY) or []
        )
        user_text = ""
        user_content = callback_context.user_content
        if user_content and user_content.parts:
            user_text = "".join(
                part.text for part in user_content.parts if part.text
            )
        allowed = {canonical(token) for token in tool_values}
        allowed.update(canonical(token) for token in value_tokens(user_text))

        changed = False
        new_parts: list[types.Part] = []
        for part in content.parts:
            if not part.text:
                new_parts.append(part)
                continue
            clean, misses = diff_reply(part.text, allowed, tool_values)
            if misses:
                changed = True
                for miss in misses:
                    logger.warning(
                        "VOICE_WHITELIST miss: model emitted %r, not among the"
                        " %d value(s) tools returned this turn; re-emitted"
                        " from tool results",
                        miss,
                        len(tool_values),
                    )
                new_parts.append(types.Part(text=clean))
            else:
                new_parts.append(part)
        if not changed:
            return None
        patched = llm_response.model_copy(deep=True)
        patched.content = types.Content(role=content.role, parts=new_parts)
        return patched


def guard_before_tool(
    *, tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> Optional[dict[str, Any]]:
    """The root before-tool callback: the second, independent rail.

    Holds the tool allowlist even if the plugin list is ever mishandled.
    Allow is ``None``; refusal is a structured non-empty dict; never ``{}``.
    """
    if tool.name not in ALLOWED_TOOLS:
        logger.warning(
            "ROUTING_GUARD (root callback) refused tool %r", tool.name
        )
        return refusal("TOOL_NOT_ALLOWLISTED")
    return None
