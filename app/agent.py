"""DISPATCHER topology: the root chat-mode agent and its ADK App.

PRD #34 (ADR-0004 decisions): the root DISPATCHER is a chat-mode LlmAgent —
the only voice the user hears. ``read_narrative`` runs in the root
before-agent callback, strictly before DISPATCHER's turn, never parallel;
its CaseDelta is merged deterministically into ``state["case"]`` by
``merge_case``. The App is constructed with ``App(plugins=[...])``, never
``Runner(plugins=...)``. The dev UI is never deployed.

DEBUNKER and PROOF_BUILDER are single-turn specialist sub-agents
(ADR-0004): google-adk 2.8.0 auto-wraps each ``mode='single_turn'``
sub-agent as a tool named after the agent, with its typed
``input_schema`` as the parameters — no ``AgentTool``, and no free-text
request parameter anywhere. Their tool calls cross ROUTING_GUARD like
DISPATCHER's own.

EMERGENCY (issue #41): the ONLY LLM transfer target in this topology. A
sub-agent of DISPATCHER with ``disallow_transfer_to_parent=True`` and no
``mode`` declared (mode=None auto-promotes to 'chat' in google-adk==2.8.0,
so it stays a transfer target — never 'single_turn'). It converses,
decides what to ask and when to stop; exit is a UI tap (mark_safe) only,
never something EMERGENCY itself decides or a model infers from her words.

Because ``disallow_transfer_to_parent=True`` also makes
``_is_transferable_across_agent_tree`` return False for EMERGENCY (verified
against the pinned 2.8.0 wheel), ADK's own "resume last active sub-agent"
routing does NOT keep her in EMERGENCY on the next turn — the fallback is
``root_agent`` (DISPATCHER). So DISPATCHER's own instruction re-transfers
to EMERGENCY, unconditionally, on every turn while the Imminent Danger
predicate is active on her Case — the predicate the app itself owns
(``app.case.is_imminent_danger``), never a fact EMERGENCY's own words are
trusted to set or clear.
"""

from __future__ import annotations

import datetime
import json

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.apps import App
from google.adk.models import BaseLlm

from app.case import is_imminent_danger, merge_case, needs_resume_check, record_emergency_turn
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
    if is_imminent_danger(case):
        if readonly_context.state.get("temp:resume_check"):
            # A long silence has passed while the predicate was active.
            # Re-ask once instead of silently resuming deep inside
            # EMERGENCY, as if the gap never happened.
            return """\
You are DISPATCHER for Gabay OFW. The Imminent Danger predicate is still
ACTIVE for this user, but a long silence has passed since her last
message. Do NOT call any tool and do NOT transfer yet. Reply warmly in
her language, check in once — ask simply how she is doing right now —
and let her answer before anything else happens. Do this only this one
turn.
"""
        # The Imminent Danger predicate is code-owned (app.case), never a
        # fact this instruction asks the model to judge. While it is
        # active, EVERY turn transfers to EMERGENCY immediately — ADK does
        # not resume a disallow_transfer_to_parent sub-agent across turns
        # on its own (verified against google-adk==2.8.0), so this
        # instruction is what keeps her in EMERGENCY, turn after turn,
        # until a UI tap (mark_safe) clears the predicate.
        return """\
You are DISPATCHER for Gabay OFW. The Imminent Danger predicate is
currently ACTIVE for this user. You must NOT reply to her yourself and
you must NOT call any tool. Your only action this turn is to call
transfer_to_agent with agent_name="EMERGENCY". Do this immediately,
every time, for every message, until the app tells you the predicate is
no longer active.
"""
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
repeat herself). The UI renders this Case directly, correctable in one
tap; a claim's ``conflicts`` list is a genuine unresolved disagreement
between sources (e.g. what she told you vs. what a document said) —
never silently pick one. If a claim relevant to her country, tenure
situation, or a grievance carries a conflict, that IS your one question
this turn: name the two values plainly and ask which is right:
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

{FILING_SEQUENCER_NAME} returns exactly one of four shapes:
- {{"plan": {{...}}}} — a verified, cited filing Plan. Walk her through
  its steps in order, in your own warm words, always naming the citation
  each step carries. A step whose citation says "the MWO can confirm"
  must be presented as something to confirm with the MWO, never as a
  flat fact, and never as a countdown.
- {{"held_refusal": {{...}}}} — her country has no verified filing
  sequence yet. Say so plainly and warmly, give her the card's MWO
  contact and 1348, and tell her not to leave before speaking to the
  MWO. Never invent a sequence to fill the gap.
- {{"unresolved_conflict": {{"field": "..."}}}} — her Case shows two
  disagreeing values for that field (e.g. she said one country, a
  document said another) and neither has been resolved by her tap. This
  becomes your ONE question this turn: name plainly what the two values
  are (from the Case above) and ask her which is right — she resolves it
  with a one-tap correction, never by you guessing or picking one for
  her. Do not call {FILING_SEQUENCER_NAME} again until she has.
- {{"no_verified_plan": true}} — the app could not build a plan it can
  stand behind. Call safe_floor_card yourself instead; never repeat the
  call to {FILING_SEQUENCER_NAME} hoping for a different result.
"""


def _emergency_instruction(readonly_context: ReadonlyContext) -> str:
    case = readonly_context.state.get("case") or {}
    case_block = json.dumps(case, ensure_ascii=False) if case else "{}"
    return f"""\
You are EMERGENCY for Gabay OFW. DISPATCHER has just transferred this
conversation to you because the Imminent Danger predicate is active: an
acute safety disclosure or her own tap on the emergency button. You are
now the only voice she hears until she taps "I'm safe" in the app — you
never decide when this conversation ends, and you never tell her to say
a phrase to exit; exit is a UI tap only, never something you infer from
her words. A textual "I'm okay" does NOT end this conversation.

Converse with her. Decide what to ask and when to stop asking, one
gentle question at a time. Stay warm, calm, and concrete; never lecture,
never promise an outcome, never invent phone numbers, deadlines, laws,
or amounts, and never direct her to local police. Reply in the language
of her current message — Tagalog in, Tagalog out; Taglish in, Taglish
out; Cebuano in, Cebuano out; English in, English out.

What the app has understood so far (her Case, structured facts with
provenance):
{case_block}

If she needs contact numbers, they must come only from office_directory
and action_card — never from memory. Never attempt to transfer this
conversation anywhere; you have no way back to DISPATCHER and none is
needed — the app itself decides when she has left EMERGENCY.
"""


def make_absorb_narrative_callback(llm: BaseLlm):
    """The root before-agent callback: read_narrative -> merge_case.

    Runs strictly before DISPATCHER's turn. On extraction failure the Case
    is left unchanged and a ``temp:`` marker (never persisted) lets the
    instruction ask one warm question instead. Always returns None so the
    DISPATCHER turn itself is never skipped.
    """

    async def absorb_narrative(*, callback_context: CallbackContext) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        case = callback_context.state.get("case")
        if is_imminent_danger(case):
            # Long-gap resume (issue #41): decide, BEFORE narrative
            # reading, whether DISPATCHER should re-ask once rather than
            # silently resuming inside EMERGENCY. Recorded here (not in
            # the instruction) so the once-only latch is set exactly
            # when this turn is actually processed.
            resume_check = needs_resume_check(case, now=now)
            callback_context.state["temp:resume_check"] = resume_check
            callback_context.state["case"] = record_emergency_turn(
                case, now=now, resume_check_issued=resume_check
            )
            if resume_check:
                # Still record the narrative for the Case, but the
                # re-ask itself is DISPATCHER's job this turn — not
                # EMERGENCY's — so no further absorb_narrative behavior
                # changes; the instruction reads temp:resume_check.
                pass
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
        callback_context.state["case"] = merge_case(
            case, delta, source="extraction", now=now
        )
        return None

    return absorb_narrative


def build_adk_app(llm: BaseLlm) -> App:
    """Builds the ADK App: DISPATCHER as the chat-mode root agent, with
    FILING_SEQUENCER, DEBUNKER, and PROOF_BUILDER as single-turn
    specialist sub-agents (ADR-0004) and EMERGENCY as its one and only
    LLM transfer sub-agent (issue #41).

    Specialists are single-turn sub-agents: google-adk 2.8.0 auto-wraps
    each ``mode='single_turn'`` sub-agent as a tool named after the
    agent, with its typed ``input_schema`` as the parameters — no
    ``AgentTool``, and no free-text request parameter anywhere. Their
    tool calls cross ROUTING_GUARD like DISPATCHER's own. EMERGENCY is
    not single_turn, so it stays a regular sub-agent and a valid
    transfer_to_agent target instead of being auto-wrapped as a tool.
    """
    filing_sequencer = build_filing_sequencer(llm)
    emergency = LlmAgent(
        name="EMERGENCY",
        # No mode declared: mode=None auto-promotes to 'chat' in
        # google-adk==2.8.0, which is required to remain a transfer
        # target for transfer_to_agent — 'single_turn' would not.
        model=llm,
        description=(
            "The Imminent Danger conversation. DISPATCHER transfers here"
            " whenever the app's Imminent Danger predicate is active; exit"
            " is a UI tap (mark_safe) only."
        ),
        instruction=_emergency_instruction,
        # disallow_transfer_to_parent=True is the one-way door: EMERGENCY
        # can never transfer_to_agent back to DISPATCHER itself. This also
        # means ADK will not resume EMERGENCY automatically on the next
        # turn (see module docstring) — DISPATCHER's own instruction is
        # what re-transfers every subsequent turn while the predicate
        # holds.
        disallow_transfer_to_parent=True,
        tools=[office_directory, action_card],
        before_tool_callback=guard_before_tool,
    )
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
        # EMERGENCY (issue #41) is different: it is NOT single_turn, so it
        # stays a normal sub-agent and a valid transfer_to_agent target
        # instead of being auto-wrapped into a tool.
        sub_agents=[
            filing_sequencer,
            build_debunker(llm),
            build_proof_builder(llm),
            emergency,
        ],
        # ROUTING_GUARD's second, independent rail (the first is the App
        # plugin below): the tool allowlist holds even if the plugin list
        # is ever mishandled. Returns None to allow — never {}.
        before_tool_callback=guard_before_tool,
    )
    return App(
        name=APP_NAME, root_agent=dispatcher, plugins=[RoutingGuardPlugin()]
    )
