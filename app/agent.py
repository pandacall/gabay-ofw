"""DISPATCHER topology: the root chat-mode agent and its ADK App.

PRD #34 (ADR-0004 decisions): the root DISPATCHER is a chat-mode LlmAgent —
the only voice the user hears. ``read_narrative`` runs in the root
before-agent callback, strictly before DISPATCHER's turn, never parallel;
its CaseDelta is merged deterministically into ``state["case"]`` by
``merge_case``. The App is constructed with ``App(plugins=[...])``, never
``Runner(plugins=...)``. The dev UI is never deployed.
"""

from __future__ import annotations

import datetime
import json

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.apps import App
from google.adk.models import BaseLlm

from app.case import merge_case
from app.extraction import read_narrative

# Exact pins (PRD #34): google-adk==2.8.0 in requirements.txt, and the
# Gemini model string pinned exactly — never a -latest alias.
GEMINI_MODEL = "gemini-2.5-flash"
APP_NAME = "gabay-ofw"

# The fixed acknowledgement the app streams before any model runs. Turn 1
# is English by design (neutral among Philippine languages); from turn 2 it
# mirrors the language recorded on the previous turn's CaseDelta.
ACKNOWLEDGEMENTS = {
    "en": "I hear you. I'm reading what you wrote — one moment.",
    "tl": "Naririnig kita. Binabasa ko ang isinulat mo — sandali lang.",
    "taglish": "Naririnig kita. Binabasa ko lang ang message mo — one moment.",
    "ceb": "Nadungog ko ikaw. Ginabasa nako ang imong gisulat — kadiyot lang.",
}


def acknowledgement_for(language: str | None) -> str:
    """The fixed acknowledgement for a recorded language; English when none."""
    return ACKNOWLEDGEMENTS.get(language or "en", ACKNOWLEDGEMENTS["en"])


def _dispatcher_instruction(readonly_context: ReadonlyContext) -> str:
    case = readonly_context.state.get("case") or {}
    extraction_failed = bool(readonly_context.state.get("temp:extraction_failed"))
    case_block = json.dumps(case, ensure_ascii=False) if case else "{}"
    failure_block = (
        "\nThis turn's narrative reading failed, so nothing new was recorded."
        " Reply warmly, do not mention any technical problem, and ask at most"
        " ONE gentle question to keep her talking.\n"
        if extraction_failed
        else ""
    )
    return f"""\
You are DISPATCHER for Gabay OFW, the only voice a Filipino overseas worker
in the Gulf hears. She may be in crisis, writing at night, in any order and
any language. You are warm, calm, and concrete. You never lecture.

Language: reply in the language of the user's CURRENT message — Tagalog in,
Tagalog out; Taglish in, Taglish out; Cebuano in, Cebuano out; English in,
English out. Follow her if she switches mid-conversation.

Keep office names, form titles, and legal terms exactly as they are, never
translated: DOLE-SEnA, SEnA, MWO, OWWA, DMW, iqama, kafala, Request for
Assistance.

What the app has understood so far (her Case, structured facts with
provenance — do not read it back verbatim, use it so she never has to
repeat herself):
{case_block}
{failure_block}
Ask at most one question per reply, and only for the single most useful
missing fact. Never invent phone numbers, deadlines, laws, or amounts.
Never promise an outcome. If she is in immediate danger, tell her plainly
that the app's emergency help is the fastest path.
"""


def make_absorb_narrative_callback(llm: BaseLlm):
    """The root before-agent callback: read_narrative -> merge_case.

    Runs strictly before DISPATCHER's turn. On extraction failure the Case
    is left unchanged and a ``temp:`` marker (never persisted) lets the
    instruction ask one warm question instead. Always returns None so the
    DISPATCHER turn itself is never skipped.
    """

    async def absorb_narrative(*, callback_context: CallbackContext) -> None:
        content = callback_context.user_content
        text = "".join(
            part.text
            for part in (content.parts if content and content.parts else [])
            if part.text
        )
        if not text.strip():
            return None
        delta = await read_narrative(llm=llm, text=text)
        if delta is None:
            callback_context.state["temp:extraction_failed"] = True
            return None
        case = callback_context.state.get("case")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        callback_context.state["case"] = merge_case(
            case, delta, source="extraction", now=now
        )
        return None

    return absorb_narrative


def build_adk_app(llm: BaseLlm) -> App:
    """Builds the ADK App with DISPATCHER as the chat-mode root agent."""
    dispatcher = LlmAgent(
        name="DISPATCHER",
        mode="chat",
        model=llm,
        description="The only voice: absorbs the story, replies warmly.",
        instruction=_dispatcher_instruction,
        before_agent_callback=make_absorb_narrative_callback(llm),
    )
    return App(name=APP_NAME, root_agent=dispatcher, plugins=[])
