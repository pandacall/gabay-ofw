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
from app.debunker import build_debunker
from app.extraction import read_narrative
from app.guard import RoutingGuardPlugin, guard_before_tool
from app.proof.agent import build_proof_builder
from app.sequencer_agent import FILING_SEQUENCER_NAME, build_filing_sequencer
from app.tools import action_card, office_directory, safe_floor_card

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

Contact numbers come ONLY from your tools — never from memory. Use
office_directory to list the real offices for her country, and
action_card with the row keys to hand her a card. When she needs a plan
you cannot verify — you don't know the right filing order, her country's
sequence isn't verified, or her facts changed — call safe_floor_card
with the fitting reason instead of guessing; the app shows her the card
itself, so frame it warmly in your own words without repeating the
numbers. Never direct her to local police.

When her message reports something she has been TOLD — a claimed debt
("utang mo ang placement fee"), a claimed rule or restriction ("you can't
leave until you repay", "it's legal for the employer to keep your
passport", "you need an NOC", "you must complete two years") — call
DEBUNKER with each claim exactly as she reported it and the language of
her message. The app shows her each verdict, its cited rebuttal, and any
MWO routing itself, so frame the outcome warmly in your own words without
repeating the numbers: state a FALSE plainly with its source named, keep
a rebuttal's own confirm-with-the-MWO wording where it has one, and for
NOT_COVERED tell her the MWO can verify it and the contact is on her
screen — never a bare "I don't know", and never a verdict, number, or
citation the tool did not return.

Evidence and documents: when she asks what to bring, what proof she
needs, or says she is missing a document (walang contract, walang
payslip), call the PROOF_BUILDER tool with the venue and what she holds,
per her Case. The app shows her the gap analysis itself; relay it in her
language: say its scope limit in your own words — this is what the
office will ask her for, never a prediction about her case — then make
exactly the ONE ask it returned (or, if it returned none, state what the
bundle covers and what it will not support). If she says she cannot get
something, call PROOF_BUILDER again with that artifact listed as
unobtainable — never proceed as if she had it.

When she has told you enough to know her country, her tenure situation
(still working there, left the employer but still in-country, or already
departed), and at least one concrete grievance (unpaid wages, passport
withheld, physical danger, a retaliatory status action, or a blocked
exit), call {FILING_SEQUENCER_NAME} with exactly those three facts — it
never sees this conversation, only the typed arguments you give it. Do
not call it on a guess; ask your one question first if a fact is still
missing.

{FILING_SEQUENCER_NAME} returns exactly one of three shapes:
- {{"plan": {{...}}}} — a verified, cited filing Plan. Walk her through
  its steps in order, in your own warm words, always naming the citation
  each step carries. A step whose citation says "the MWO can confirm"
  must be presented as something to confirm with the MWO, never as a
  flat fact, and never as a countdown.
- {{"held_refusal": {{...}}}} — her country has no verified filing
  sequence yet. Say so plainly and warmly, give her the card's MWO
  contact and 1348, and tell her not to leave before speaking to the
  MWO. Never invent a sequence to fill the gap.
- {{"no_verified_plan": true}} — the app could not build a plan it can
  stand behind. Call safe_floor_card yourself instead; never repeat the
  call to {FILING_SEQUENCER_NAME} hoping for a different result.
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
    """Builds the ADK App with DISPATCHER as the chat-mode root agent.

    Specialists are single-turn sub-agents (ADR-0004): google-adk 2.8.0
    auto-wraps each ``mode='single_turn'`` sub-agent as a tool named
    after the agent, with its typed ``input_schema`` as the parameters —
    no ``AgentTool``, and no free-text request parameter anywhere. Their
    tool calls cross ROUTING_GUARD like DISPATCHER's own.
    """
    filing_sequencer = build_filing_sequencer(llm)
    dispatcher = LlmAgent(
        name="DISPATCHER",
        mode="chat",
        model=llm,
        description="The only voice: absorbs the story, replies warmly.",
        instruction=_dispatcher_instruction,
        before_agent_callback=make_absorb_narrative_callback(llm),
        tools=[office_directory, action_card, safe_floor_card],
        # FILING_SEQUENCER (issue #42) is NOT listed in tools=[...]: as a
        # mode='single_turn' sub_agent, google-adk's LlmAgent.model_post_init
        # auto-wraps it into a single tool of this same name and appends it
        # to DISPATCHER's tools itself. No AgentTool(...) here (PRD #34).
        # DEBUNKER and PROOF_BUILDER (issues #47/#45) are wired the same way.
        sub_agents=[
            filing_sequencer,
            build_debunker(llm),
            build_proof_builder(llm),
        ],
        # ROUTING_GUARD's second, independent rail (the first is the App
        # plugin below): the tool allowlist holds even if the plugin list
        # is ever mishandled. Returns None to allow — never {}.
        before_tool_callback=guard_before_tool,
    )
    return App(
        name=APP_NAME, root_agent=dispatcher, plugins=[RoutingGuardPlugin()]
    )
