"""DISPATCHER topology: the root chat-mode agent and its ADK App.

PRD #34 (ADR-0004 decisions): the root DISPATCHER is a chat-mode LlmAgent —
the only voice the user hears. ``read_narrative`` runs in the root
before-agent callback, strictly before DISPATCHER's turn, never parallel;
its CaseDelta is merged deterministically into her user-scoped Case
(``app.state_keys.CASE``) by ``merge_case``. The App is constructed
with ``App(plugins=[...])``, never
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

Bounded context growth (issue #49): every specialist (FILING_SEQUENCER,
DEBUNKER, PROOF_BUILDER, COMPLAINT_DRAFTER, RECOURSE_ROUTER) is a tool call
whose full return value is replayed into DISPATCHER's context on every
subsequent turn — a long crisis conversation with several specialist calls
grows without bound unless the App itself compacts it. ``App(...)`` below
sets ``events_compaction_config`` (an ``LlmEventSummarizer`` sliding-window
plus a token-threshold safety net, verified against the pinned 2.8.0 wheel
at ``google/adk/apps/app.py:84``) and ``context_cache_config`` (the wheel's
default cache window, ``google/adk/apps/app.py:87``) so replay cost and
per-turn latency stay bounded through a long demo session rather than
growing turn over turn.
"""

from __future__ import annotations

import datetime
import json

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.apps import App
from google.adk.apps._configs import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import BaseLlm

from app.case import is_imminent_danger, merge_case, needs_resume_check, record_emergency_turn
from app.complaint.agent import COMPLAINT_DRAFTER_NAME, build_complaint_drafter
from app.debunker import build_debunker
from app.directory import resolve_case_country
from app.extraction import read_narrative
from app.guard import RoutingGuardPlugin, guard_before_tool
from app.proof.agent import build_proof_builder
from app.recourse.agent import RECOURSE_ROUTER_NAME, build_recourse_router
from app.rules import Jurisdiction
from app.sequencer import Plan, SequencerIn
from app.sequencer_agent import FILING_SEQUENCER_NAME, build_filing_sequencer
from app.staleness import apply_step_expiry, is_input_stale
from app.state_keys import (
    CASE,
    CASE_MUTATIONS,
    PLAN,
    PLAN_ACTIVE,
    PLAN_MUTATIONS,
    PLAN_SEQ_IN,
)
from app.tools import (
    action_card,
    mark_plan_step_done,
    office_directory,
    safe_floor_card,
)

# Exact pins (PRD #34): google-adk==2.8.0 in requirements.txt, and the
# Gemini model string pinned exactly — never a -latest alias.
GEMINI_MODEL = "gemini-3.6-flash"
APP_NAME = "gabay-ofw"

# Bounded context growth (issue #49): compaction trigger policy for
# build_events_compaction_config below. Two independent triggers, either
# of which fires compaction — a sliding invocation-count window (every N
# new user-initiated turns, keeping some overlap for continuity across
# the summary boundary) and a token-threshold safety net for a single
# turn that grows unusually large (e.g. a long FILING_SEQUENCER or
# COMPLAINT_DRAFTER return value replayed into DISPATCHER's context).
_COMPACTION_INVOCATION_INTERVAL = 6
_COMPACTION_OVERLAP_INVOCATIONS = 2
_COMPACTION_TOKEN_THRESHOLD = 6000
_COMPACTION_RETAINED_RAW_EVENTS = 10

# The fixed acknowledgement the app streams before any model runs. Turn 1
# is English by design (neutral among Philippine languages); from turn 2 it
# mirrors the language recorded on the previous turn's CaseDelta.
ACKNOWLEDGEMENTS = {
    "en": "I hear you. I'm reading what you wrote — one moment.",
    "tl": "Naririnig kita. Binabasa ko ang isinulat mo — sandali lang.",
    "ceb": "Nadungog ko ikaw. Ginabasa nako ang imong gisulat — kadiyot lang.",
}

# Reply-language ruling (issue #67): Taglish is a closed-set DETECTION
# value on CaseDelta.language, never a language the app produces text in.
# A recorded "taglish" renders with the pure Filipino acknowledgement —
# same as "tl" — never a Taglish-worded one.
_FILIPINO_LANGUAGES = frozenset({"tl", "taglish"})


def acknowledgement_for(language: str | None) -> str:
    """The fixed acknowledgement for a recorded language; English when
    none, unrecognized, or "taglish" is normalized to the pure Filipino
    text (issue #67: never a Taglish-worded acknowledgement)."""
    if language in _FILIPINO_LANGUAGES:
        language = "tl"
    return ACKNOWLEDGEMENTS.get(language or "en", ACKNOWLEDGEMENTS["en"])


# ---------------------------------------------------------------------------
# The Progress Trail (issue #75, ADR-0010): a fixed, code-owned label per
# specialist tool CALL, plus FILING_SEQUENCER's verification step. Never
# the model's own thought summaries — see the ADR for why. Translated
# exactly like ACKNOWLEDGEMENTS above (same closed language set, same
# "taglish" -> pure Filipino normalization).
# ---------------------------------------------------------------------------

# The trail's opening line: fires immediately after the acknowledgement,
# before any tool call, since reasoning and extraction happen before any
# tool call. Deliberately NOT "reading what you wrote" — the
# acknowledgement already says that; this is the next beat, what the app
# is about to do.
PROGRESS_TRAIL_OPENING = {
    "en": "Now let's see what would help you here.",
    "tl": "Ngayon, tingnan natin kung ano ang makakatulong sa iyo.",
    "ceb": "Karon, tan-awon nato kung unsa ang makatabang nimo.",
}

#: One fixed label per specialist tool-CALL name DISPATCHER (or a
#: specialist, for the verification entry) may fire, keyed exactly to the
#: name google-adk exposes the call under — never a raw tool name, an
#: agent name, or JSON shown to her. Every key here names the TASK, never
#: a hypothesis about her situation (ADR-0010): "Checking what the rules
#: actually say", never a claim about whether she was lied to. The ADR's
#: own "Looking up your agency" example names COMPLAINT_DRAFTER's
#: INTERNAL agency-license check (``complaint_check_agency_license``) —
#: an internal tool, so per the granularity rule below it gets no line of
#: its own; COMPLAINT_DRAFTER's ONE line names what the specialist as a
#: whole is doing (drafting/filling the complaint), never the narrower
#: internal check.
#:
#: Granularity (ADR-0010's "one line per specialist, plus one for
#: verification"): FILING_SEQUENCER's OWN internal tools
#: (sequencer_jurisdiction_rules, sequencer_sequence_actions,
#: sequencer_compute_deadlines) are deliberately ABSENT — only the
#: specialist call itself and its verification step
#: (sequencer_verify_plan) get a line, so a single filing turn never
#: stutters four lines through what she asked as one question. The same
#: reasoning drops DEBUNKER's own search_corpus, COMPLAINT_DRAFTER's four
#: gate/fill tools (including complaint_check_agency_license), and
#: RECOURSE_ROUTER's recourse_build_routes — each is covered by its
#: specialist's one line already. Contact-directory and card-rendering
#: tools (office_directory, action_card, safe_floor_card,
#: mark_plan_step_done) are absent too: the card itself appears, which
#: says more than a label could. Any call whose name is not a key here
#: renders NOTHING (the quiet-gap failure mode ADR-0010 requires).
PROGRESS_TRAIL_LABELS: dict[str, dict[str, str]] = {
    "DEBUNKER": {
        "en": "Checking what the rules actually say.",
        "tl": "Tinitingnan kung ano talaga ang sinasabi ng batas.",
        "ceb": "Gitan-aw kung unsa gyud ang giingon sa balaod.",
    },
    "PROOF_BUILDER": {
        "en": "Working out what proof you already have.",
        "tl": "Tinitingnan kung anong patunay ang mayroon ka na.",
        "ceb": "Gitan-aw kung unsa nga pamatuod anaa na nimo.",
    },
    "FILING_SEQUENCER": {
        "en": "Working out your filing steps in order.",
        "tl": "Inaayos ang pagkakasunud-sunod ng dapat mong gawin.",
        "ceb": "Gihan-ay ang han-ay sa imong buhaton.",
    },
    # The verification exception (ADR-0010): sequencer_verify_plan is
    # FILING_SEQUENCER's OWN tool call, distinct from the specialist line
    # above, because "checking these steps against the rules" is a
    # separate, true claim and the most reassuring thing the system can
    # say to someone a recruiter has lied to.
    "sequencer_verify_plan": {
        "en": "Checking these steps against the rules.",
        "tl": "Tinitingnan kung tama ang mga hakbang na ito ayon sa batas.",
        "ceb": "Gisusi kung husto kini nga mga lakang base sa balaod.",
    },
    # Names the specialist's whole task (drafting/filling the complaint
    # form), never the narrower internal agency-license check it also
    # runs — that check (complaint_check_agency_license) is an internal
    # tool and stays silent, per the granularity rule above.
    "COMPLAINT_DRAFTER": {
        "en": "Putting your complaint into the right form.",
        "tl": "Inilalagay ang reklamo mo sa tamang porma.",
        "ceb": "Gibutang ang imong reklamo sa hustong porma.",
    },
    "RECOURSE_ROUTER": {
        "en": "Working out where you can take this next.",
        "tl": "Tinitingnan kung saan mo pwedeng dalhin ito.",
        "ceb": "Gitan-aw kung asa nimo kini madala.",
    },
}


def _closed_language(language: str | None) -> str:
    """The same normalization ``acknowledgement_for`` applies: "taglish"
    folds to "tl" (issue #67 — Taglish is detected, never produced), and
    anything else falls through to the caller's own English default."""
    return "tl" if language in _FILIPINO_LANGUAGES else (language or "en")


def progress_trail_opening_for(language: str | None) -> str:
    """The trail's fixed opening line for a recorded language — same
    closed language set and source of truth as ``acknowledgement_for``."""
    return PROGRESS_TRAIL_OPENING.get(
        _closed_language(language), PROGRESS_TRAIL_OPENING["en"]
    )


def progress_trail_label_for(call_name: str, language: str | None) -> str | None:
    """The fixed label for a tool/specialist CALL name, or ``None`` when
    ``call_name`` has no entry in :data:`PROGRESS_TRAIL_LABELS` — the
    quiet-gap failure mode ADR-0010 requires (never a raw tool name, an
    agent name, or JSON on screen)."""
    labels = PROGRESS_TRAIL_LABELS.get(call_name)
    if labels is None:
        return None
    return labels.get(_closed_language(language), labels["en"])


def _dispatcher_instruction(readonly_context: ReadonlyContext) -> str:
    case = readonly_context.state.get(CASE) or {}
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
            recorded_language = case.get("language") or "unknown"
            return f"""\
You are DISPATCHER for Gabay OFW. The Imminent Danger predicate is still
ACTIVE for this user, but a long silence has passed since her last
message. Do NOT call any tool and do NOT transfer yet. Reply warmly,
check in once — ask simply how she is doing right now — and let her
answer before anything else happens. Language (issue #67 ruling, same
closed set as every DISPATCHER reply): her Case records "language" as
{recorded_language!r} — ENGLISH by default ("unknown", "en", or "other"),
PURE Filipino for "tl" or "taglish" (Taglish is detected, never
produced), PURE Cebuano/Bisaya for "ceb". Do this only this one turn.
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
    plan_active = readonly_context.state.get(PLAN_ACTIVE)
    stale_block = (
        "\nHer previously verified Plan just went inactive because"
        " something she told you changed (ADR-0006, issue #43) — the app"
        " is already showing her the Safe Floor. In your reply, name the"
        " specific fact from her Case above that changed (\"this needs"
        " updating because you told me X\") rather than a generic"
        " apology. Do not describe the old plan's steps as current; if"
        " you now have her country, tenure, and grievances, call"
        f" {FILING_SEQUENCER_NAME} again to try to verify a replacement.\n"
        if plan_active is False
        else ""
    )
    return f"""\
You are DISPATCHER for Gabay OFW, the only voice a Filipino overseas worker
in the Gulf hears. She may be in crisis, writing at night, in any order and
any language. You are warm, calm, and concrete. You never lecture.

Language (issue #67 ruling — a closed set, ENGLISH is the default): reply
in ENGLISH unless the Case below records "language" as "tl", "taglish", or
"ceb". "tl" -> reply in PURE Filipino, no English code-switching beyond
the untranslated terms below. "taglish" -> ALSO reply in PURE Filipino —
Taglish is a language you detect in what she writes, never one you write
yourself, so a Taglish message still gets a pure Filipino reply, never a
mixed one. "ceb" -> reply in pure Cebuano/Bisaya, same purity rule. Turn
one, an unrecorded language, "en", or "other" all mean ENGLISH. Follow her
if she switches mid-conversation; never mix English and Filipino (or
English and Cebuano) in the same reply.

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
{failure_block}{stale_block}
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
  call to {FILING_SEQUENCER_NAME} hoping for a different result. If this
  response ALSO carries "regeneration_failed": true (issue #43: her
  previously verified plan's replacement failed to verify after her
  facts changed), ALSO call action_card with her country's MWO and OWWA
  contact keys — she needs the Safe Floor PLUS a concrete action card
  here, never the Safe Floor alone, and never the failed replacement or
  her old plan presented as current.

If a "delta" accompanies a plan (issue #43: it was regenerated from a
prior one), tell her plainly what changed — which steps are new, which
no longer apply — and, if any of her earlier steps carried over as
already done, say so instead of walking her through them again. Never
silently reorder her plan without saying what changed.

When she tells you she has already completed one of her Plan's steps
(she already filed the SEnA request, she already reported it), call
mark_plan_step_done with that Plan's plan_id and the step's id, both
exactly as shown to her. The app re-renders the updated plan itself;
acknowledge it warmly, and never mark a step done on a guess.

Once she has a verified Plan and she asks about filing a complaint, what
to bring, or wants her SEnA form or intake papers, call
{COMPLAINT_DRAFTER_NAME} with her worker/employer/agency identity, her
country, tenure, grievances, an optional wage-loss figure, and any
safety flags — it never sees this conversation, only the typed
arguments you give it. It fills forms, it NEVER submits anything.

{COMPLAINT_DRAFTER_NAME} returns exactly one of three shapes; frame
whichever one it returns warmly in her language on screen (the closed
set above — English by default, pure Filipino, or pure Cebuano; never
Taglish), the same as every other specialist result — the fixed form
fields and PDF stay in English, but how you tell her about them follows
that same rule:
- {{"draft": {{...}}}} — a red-team-cleared SEnA RFA (rendered as a
  PDF), an English MWO/ATN intake narrative, and (when a wage-loss
  figure was given) the Arabic arithmetic-only loss calculation. Tell
  her the form is filled and ready for her to review and file herself —
  never say it has been filed or sent anywhere.
- {{"illegal_recruitment_refusal": {{...}}}} — her agency is not shown
  licensed, or she was hired directly. Say plainly that SEnA is the
  wrong office for this and relay the illegal-recruitment routing the
  card carries; never draft a form for the wrong venue yourself.
- {{"premature_filing_refusal": {{...}}}} — she has an urgent safety
  grievance and has not yet left her employer. Say plainly that filing
  now risks exposing her before she is safely out, and point her to the
  MWO / Safe Floor instead; never push her toward filing regardless.

When she asks which recourses are open to her, what office to go to, or
whether her family back home can act for her, call {RECOURSE_ROUTER_NAME}
with her country, tenure, grievances, her recruitment agency (or
direct-hire flag), and her family's location in the Philippines if she
has told you (Metro Manila or elsewhere) — it never sees this
conversation, only the typed arguments you give it.

{RECOURSE_ROUTER_NAME} returns {{"routes": [...]}}: every open door for
her situation, each naming a venue, an executor (whether she herself can
act, only a family member can, or either can), what must be true first,
and what to bring. Walk her through EVERY route it returned, in order,
in your own warm words — never drop one, never add one, and never
invent a venue, an executor, or a prerequisite it did not return. Say
plainly, for each route, whether she can do it herself from where she
is (executor "self" or "either") or whether it needs her family in the
Philippines (executor "kin"); never assume she has to wait until she is
home. Contact numbers still come only from office_directory and
action_card — never repeat a phone number {RECOURSE_ROUTER_NAME} did not
return, since it does not return any.
"""


def _emergency_instruction(readonly_context: ReadonlyContext) -> str:
    case = readonly_context.state.get(CASE) or {}
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
or amounts, and never direct her to local police. Language (issue #67
ruling, same closed set as DISPATCHER): reply in ENGLISH by default, or
in PURE Filipino when the Case below records "language" as "tl" or
"taglish" (Taglish is detected, never produced — it always renders as
pure Filipino, never mixed), or in pure Cebuano/Bisaya when it records
"ceb". Never mix English and Filipino (or English and Cebuano) in the
same reply.

What the app has understood so far (her Case, structured facts with
provenance):
{case_block}

If she needs contact numbers, they must come only from office_directory
and action_card — never from memory. Never attempt to transfer this
conversation anywhere; you have no way back to DISPATCHER and none is
needed — the app itself decides when she has left EMERGENCY.
"""


def _recheck_plan_staleness(
    callback_context: CallbackContext, *, plan_mutations: list[dict]
) -> None:
    """Runs both ADR-0006 staleness checks every turn, unconditionally —
    never DISPATCHER's judgement (issue #43).

    Step expiry (``apply_step_expiry``) is wall-clock-only and always
    re-applied to the persisted plan, independent of anything DISPATCHER
    does this turn. The input-hash check compares this turn's Case
    against the ``SequencerIn`` the persisted plan was published from,
    substituting in the country freshly resolved from the Case: a
    country correction is a genuine change to a real ``SequencerIn``
    field, so this is a faithful (if partial — tenure and grievances are
    free-text DISPATCHER interprets, not stored as Case claims) instance
    of ``hash(current_sequencer_in) != plan.input_hash``. A mismatch
    marks the plan inactive; ``chat.py`` renders the Safe Floor from
    that flag with zero reliance on DISPATCHER calling any tool.

    Writes ``callback_context.state`` directly too (the pre-merged
    convenience blob this turn's own reads use), but the persisted truth
    is the ``"recheck_staleness"`` mutation appended to ``plan_mutations``
    (ADR-0008 amendment): the Plan is user-scoped now and has no
    session-document revision guard, so the commit-time replay
    (``app.plan_ops``) always re-evaluates against whichever Plan is
    ACTUALLY stored — never this turn's possibly-stale copy — closing the
    race where a second Conversation's stale recheck could overwrite a
    Plan another Conversation just verified.
    """
    raw_plan = callback_context.state.get(PLAN)
    if not raw_plan:
        return None
    plan = Plan.model_validate(raw_plan)

    now = datetime.datetime.now(datetime.timezone.utc)
    voided = apply_step_expiry(plan, now=now)
    if voided is not plan:
        callback_context.state[PLAN] = voided.model_dump(mode="json")
        plan = voided

    case = callback_context.state.get(CASE)
    country = resolve_case_country(case)
    try:
        country_value: str | None = Jurisdiction(country.value).value
    except ValueError:
        # UNKNOWN/PH: no country signal to compare against — leave the
        # existing plan_active as-is (nothing derivable changed).
        country_value = None

    raw_seq_in = callback_context.state.get(PLAN_SEQ_IN)
    if raw_seq_in and country_value is not None:
        current_seq_in = SequencerIn.model_validate(
            {**raw_seq_in, "country": country_value}
        )
        # plan_active is the single source of truth chat.py reads to decide
        # whether to render the inactive-plan Safe Floor; there is only one
        # reason today (a fact changed) so no separate reason key is kept —
        # add one back if a second reason is ever introduced.
        callback_context.state[PLAN_ACTIVE] = not is_input_stale(plan, current_seq_in)

    plan_mutations.append(
        {
            "op": "recheck_staleness",
            "country": country_value,
            "now": now.isoformat(),
        }
    )
    return None


def make_absorb_narrative_callback(llm: BaseLlm):
    """The root before-agent callback: read_narrative -> merge_case, then
    the plan-staleness recheck.

    Runs strictly before DISPATCHER's turn. On extraction failure the Case
    is left unchanged and a ``temp:`` marker (never persisted) lets the
    instruction ask one warm question instead. Always returns None so the
    DISPATCHER turn itself is never skipped.
    """

    async def absorb_narrative(*, callback_context: CallbackContext) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Both the record_emergency_turn write below and the extraction
        # merge write further down can happen in THIS SAME callback, which
        # shares exactly one Event — accumulate their mutations in local
        # lists and write each temp: key once at the end (ADR-0008).
        # Reading it back out of state to append would leak an
        # already-persisted mutation forward into a LATER event this same
        # invocation and re-apply it a second time.
        case_mutations: list[dict] = []
        plan_mutations: list[dict] = []
        case = callback_context.state.get(CASE)
        if is_imminent_danger(case):
            # Long-gap resume (issue #41): decide, BEFORE narrative
            # reading, whether DISPATCHER should re-ask once rather than
            # silently resuming inside EMERGENCY. Recorded here (not in
            # the instruction) so the once-only latch is set exactly
            # when this turn is actually processed.
            resume_check = needs_resume_check(case, now=now)
            callback_context.state["temp:resume_check"] = resume_check
            callback_context.state[CASE] = record_emergency_turn(
                case, now=now, resume_check_issued=resume_check
            )
            case_mutations.append(
                {
                    "op": "record_emergency_turn",
                    "now": now,
                    "resume_check_issued": resume_check,
                }
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
        if text.strip():
            delta = await read_narrative(llm=llm, text=text)
            if delta is None:
                callback_context.state["temp:extraction_failed"] = True
            else:
                case = callback_context.state.get(CASE)
                callback_context.state[CASE] = merge_case(
                    case, delta, source="extraction", now=now
                )
                case_mutations.append(
                    {
                        "op": "merge",
                        "delta": delta,
                        "source": "extraction",
                        "now": now,
                    }
                )
        _recheck_plan_staleness(callback_context, plan_mutations=plan_mutations)
        if case_mutations:
            callback_context.state[CASE_MUTATIONS] = case_mutations
        if plan_mutations:
            callback_context.state[PLAN_MUTATIONS] = plan_mutations
        return None

    return absorb_narrative


def build_adk_app(llm: BaseLlm) -> App:
    """Builds the ADK App: DISPATCHER as the chat-mode root agent, with
    FILING_SEQUENCER, DEBUNKER, PROOF_BUILDER, COMPLAINT_DRAFTER, and
    RECOURSE_ROUTER as single-turn specialist sub-agents (ADR-0004) and
    EMERGENCY as its one and only LLM transfer sub-agent (issue #41).

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
        tools=[office_directory, action_card, safe_floor_card, mark_plan_step_done],
        # FILING_SEQUENCER (issue #42) is NOT listed in tools=[...]: as a
        # mode='single_turn' sub_agent, google-adk's LlmAgent.model_post_init
        # auto-wraps it into a single tool of this same name and appends it
        # to DISPATCHER's tools itself. No AgentTool(...) here (PRD #34).
        # DEBUNKER and PROOF_BUILDER (issues #47/#45) are wired the same way.
        # EMERGENCY (issue #41) is different: it is NOT single_turn, so it
        # stays a normal sub-agent and a valid transfer_to_agent target
        # instead of being auto-wrapped into a tool. COMPLAINT_DRAFTER
        # (issue #46) and RECOURSE_ROUTER (issue #48) are wired the same
        # single_turn way as the others.
        sub_agents=[
            filing_sequencer,
            build_debunker(llm),
            build_proof_builder(llm),
            emergency,
            build_complaint_drafter(llm),
            build_recourse_router(llm),
        ],
        # ROUTING_GUARD's second, independent rail (the first is the App
        # plugin below): the tool allowlist holds even if the plugin list
        # is ever mishandled. Returns None to allow — never {}.
        before_tool_callback=guard_before_tool,
    )
    return App(
        name=APP_NAME,
        root_agent=dispatcher,
        plugins=[RoutingGuardPlugin()],
        events_compaction_config=build_events_compaction_config(llm),
        context_cache_config=ContextCacheConfig(),
    )


def build_events_compaction_config(llm: BaseLlm) -> EventsCompactionConfig:
    """Bounds per-turn replay cost as a crisis conversation grows long.

    Two independent triggers (issue #49), either of which fires compaction:
    a sliding window by invocation count and a token-threshold safety net
    for a single turn that grows unusually large (e.g. a long
    FILING_SEQUENCER or COMPLAINT_DRAFTER return value). ``LlmEventSummarizer``
    is the wheel's only built-in summarizer (google-adk==2.8.0); a
    ``None`` summarizer would make ``App.events_compaction_config`` a
    no-op (verified against ``google/adk/apps/compaction.py``).
    """
    return EventsCompactionConfig(
        summarizer=LlmEventSummarizer(llm=llm),
        compaction_interval=_COMPACTION_INVOCATION_INTERVAL,
        overlap_size=_COMPACTION_OVERLAP_INVOCATIONS,
        token_threshold=_COMPACTION_TOKEN_THRESHOLD,
        event_retention_size=_COMPACTION_RETAINED_RAW_EVENTS,
    )
