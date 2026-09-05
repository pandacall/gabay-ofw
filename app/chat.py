"""The conversation spine over HTTP: acknowledgement, then the DISPATCHER turn.

The endpoint handler streams NDJSON. The first line is the fixed
acknowledgement, emitted before any model call is made (turn 1 English by
design; turn 2+ uses the language recorded on the previous turn's
CaseDelta). Then the ADK Runner drives the turn — read_narrative and
merge_case in the root before-agent callback, DISPATCHER's reply after —
and the reply plus the updated Case are streamed as further lines.

When DEBUNKER ran this turn, the ``search_corpus`` tool results are
streamed as a ``verdicts`` line: the code-owned, guard-filtered payload
(verdict, cited rebuttal, MWO routing with directory-resolved numbers)
rendered by the UI outside the LLM text, per ADR-0002. When PROOF_BUILDER
ran, its schema-validated ProofGap crosses the same seam as a
``proof_gap`` line: the scope limit, the satisfied/outstanding rows, and
the single next-artifact ask are shown by the UI from the typed payload,
so the voice only frames them. When COMPLAINT_DRAFTER ran, its
schema-validated ComplaintDraftOut crosses the same seam as a
``complaint_draft`` line — the filled SEnA RFA (with its rendered PDF),
the English intake narrative, the Arabic arithmetic-only loss
calculation, or whichever refusal fired — never framed as prose the
voice composed itself. When RECOURSE_ROUTER ran, its schema-validated
list of RecourseRoute objects crosses the same seam as a
``recourse_routes`` line — venue, executor, prerequisites, what to
bring, and source per route, never framed as prose the voice composed
itself.

``ChatService.correct_case`` (issue #44) is the one-tap correction seam:
the Case streamed on the ``case`` line is rendered and correctable by the
UI directly (never only narrated by DISPATCHER's prose), and a tap there
calls this method instead of going through a conversation turn at all.

The Progress Trail (issue #75, ADR-0010) crosses the same seam as its own
``trail`` line type: a fixed, code-owned label — never the model's own
narration — shown while the turn runs and cleared when the reply lands.
The opening ``trail`` line is emitted right after ``ack``, before the
Runner (and therefore any model) is invoked, because reasoning and
extraction happen before any tool call. Every subsequent ``trail`` line
is keyed to a tool CALL (``event.get_function_calls()``, read live as the
Runner streams events — never the tool RESULT, so the label appears
while the work is happening) against the fixed
``app.agent.PROGRESS_TRAIL_LABELS`` table; a call whose name has no entry
there emits nothing. Each specialist call fires at most once per turn
(deduplicated by call name), matching "each specialist that runs produces
exactly one line."
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import uuid4

from google.adk.events import Event, EventActions
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, Session
from google.genai import types

from app.agent import (
    APP_NAME,
    acknowledgement_for,
    build_adk_app,
    progress_trail_label_for,
    progress_trail_opening_for,
)
from app.case import ACUTE_SAFETY_FLAGS, merge_case
from app.directory import Country, resolve_case_country, resolve_keys
from app.emergency import (
    EMERGENCY_OPENER_TRIGGER,
    REASON_BUTTON,
    build_handoff,
    button_summary,
    clear_latch,
    disclosure_summary,
    empty_resume,
    is_emergency_conversation,
    open_latch,
    reason_category_for,
)
from app.history import cards_in, replay_conversation
from app.labels import (
    CONVERSATION_LABEL,
    CONVERSATION_LABEL_SOURCE,
    CONVERSATION_TITLE_LLM_ATTEMPTED,
    EMERGENCY_CONVERSATION,
    label_state_delta,
    llm_title_state_delta,
    rename_state_delta,
)
from app.reply_text import visible_texts
from app.safe_floor import CARD_KEYS, SafeFloorReason, build_card, cached_card
from app.title import ModelCall, generate_title
from app.state_keys import (
    CASE,
    CASE_MUTATIONS,
    CASE_RAW,
    EMERGENCY_CONVERSATION_ID,
    EMERGENCY_CONVERSATION_ID_RAW,
    EMERGENCY_LATCH,
    EMERGENCY_RESUME,
    ESCALATION_HANDOFF,
    PLAN_ACTIVE,
)

logger = logging.getLogger(__name__)


def _line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def reply_text_from_line(line: str) -> str | None:
    """The ``reply`` line's text out of one raw NDJSON line this module
    yielded, or ``None`` for any other line type (including malformed
    JSON). The NDJSON line shape is this module's own vocabulary
    (module docstring); ``app.main``'s title-generation trigger needs
    her turn's reply text without re-deriving that shape itself.
    """
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    if isinstance(payload, dict) and payload.get("type") == "reply":
        text = payload.get("text")
        if isinstance(text, str):
            return text
    return None


#: Card types that already tell her the state of her Plan (or its
#: replacement, per ADR-0006) — the auto-rendered inactive-plan Safe
#: Floor (below) is skipped when one of these already streamed this turn,
#: so she never sees two contradicting cards.
_PLAN_STATUS_CARD_TYPES = frozenset({"plan", "safe_floor", "held_refusal"})


def _default_action_card(country: Country) -> dict:
    """A fixed, code-owned action card of her country's MWO/OWWA contacts
    (issue #43): guarantees the "Safe Floor plus action card" consequence
    ADR-0006 requires for a failed regeneration is real even if DISPATCHER
    never calls the ``action_card`` tool itself. Reuses the same curated,
    dialability-filtered key list ``safe_floor.build_card`` renders from —
    this is deliberately the same contacts a Safe Floor card would show,
    just packaged as its own ``action_card`` alongside it.
    """
    keys = list(CARD_KEYS.get(country, CARD_KEYS[Country.UNKNOWN]))
    return {
        "type": "action_card",
        "country": country.value,
        "contacts": resolve_keys(keys, country),
    }


async def stream_stateless_fallback() -> AsyncIterator[str]:
    """The hard fallback when the session store is down: the cached Safe
    Floor card, zero model calls, nothing read or written anywhere."""
    yield _line({"type": "ack", "text": acknowledgement_for(None)})
    yield _line({"type": "card", "card": cached_card(Country.UNKNOWN)})
    yield _line({"type": "error", "detail": "session store unavailable"})


class ChatService:
    """Owns the ADK App and Runner; one instance per FastAPI app."""

    def __init__(
        self,
        *,
        session_service: BaseSessionService,
        llm: BaseLlm,
        title_model: ModelCall | None = None,
    ):
        self._session_service = session_service
        self._runner = Runner(
            app=build_adk_app(llm), session_service=session_service
        )
        # The one-time background Conversation-title call (spec
        # 2026-09-05-llm-conversation-titles): a plain out-of-band model
        # call, never the ADK Runner/DISPATCHER — None disables the
        # feature entirely (tests, or a deployment with no title model
        # configured), in which case the existing claims-based label is
        # the only source a Conversation's title ever gets.
        self._title_model = title_model

    async def get_or_create_session(
        self, *, uid: str, session_id: str | None
    ) -> Session | None:
        """Returns the user's session, creating one when no id is given.

        Returns None when an explicit id does not exist (or belongs to a
        different user — sessions live under the user's own subtree).
        """
        if session_id is None:
            return await self._session_service.create_session(
                app_name=APP_NAME, user_id=uid
            )
        return await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )

    async def list_conversations(self, *, uid: str) -> list[dict]:
        """Her Conversations, most-recent first (issue #72, ADR-0008).

        Deliberately loads no per-Conversation state — the rail is a
        list of threads, not their contents. Rows carry only an id and a
        last-activity time; the neutral date label the UI shows is
        derived from that, and denormalised topic labels arrive in a
        later slice (#73). ``list_sessions`` sorts ascending, so the
        most-recent-first ordering the rail wants is applied here.
        """
        response = await self._session_service.list_sessions(
            app_name=APP_NAME, user_id=uid
        )
        rows = [
            {
                "session_id": session.id,
                "last_update_time": session.last_update_time,
                # The denormalised topic label (issue #73), or None → the
                # UI keeps the neutral date label. Read from the session's
                # own state, which list_sessions already carries — no
                # per-Conversation state is loaded to build the rail.
                "label": (session.state or {}).get(CONVERSATION_LABEL),
                "label_source": (session.state or {}).get(CONVERSATION_LABEL_SOURCE),
            }
            for session in (response.sessions or [])
        ]
        rows.sort(key=lambda row: row["last_update_time"], reverse=True)
        return rows

    async def load_conversation(
        self, *, uid: str, session_id: str
    ) -> list[dict] | None:
        """A past Conversation's transcript as replayable stream lines
        (issue #72, ADR-0008), or ``None`` when it does not exist or
        belongs to another user — the caller renders 404 either way,
        matching ``/api/chat``'s own session lookup.

        The lines are the same NDJSON types ``stream_turn`` emits live
        (minus the transient ``ack``/``trail``), so the client renders a
        re-opened Conversation through the identical handler. A past
        deadline-bearing Plan card collapses here rather than replaying
        as actionable (``app.history``).
        """
        session = await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )
        if session is None:
            return None
        lines = replay_conversation(session.events)
        if is_emergency_conversation(session.state):
            # A re-opened Emergency Conversation (ADR-0009): tell the
            # client this thread holds the latch so it shows the
            # "I'm safe" control. Its transcript replays like any other.
            lines = [{"type": "emergency_latch", "active": True}] + lines
        return lines

    async def delete_conversation(self, *, uid: str, session_id: str) -> bool:
        """Removes one Conversation's transcript and nothing else (issue
        #72, ADR-0007 amendment). Her Case and Plan are user-scoped and
        untouched; ``delete_session`` recursively deletes only
        ``users/{uid}/sessions/{session_id}`` and its events. Returns
        whether the Conversation existed (``False`` → the caller renders
        404, never leaking another user's session id as "found").

        ADR-0009: deleting the Emergency Conversation is permitted
        UNCONDITIONALLY, including while its latch is active — deletion is
        a safety action, so refusing then would put bookkeeping above her
        safety. The latch is Conversation state and dies with the
        Conversation; only the user-scoped "one live Emergency
        Conversation" pointer needs an explicit clear, done here before
        the delete so nothing is orphaned. Her Safety Flags survive on
        the Case.
        """
        session = await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )
        if session is None:
            return False
        user_state = await self._user_state(uid=uid)
        if user_state.get(EMERGENCY_CONVERSATION_ID_RAW) == session_id:
            await self._session_service.append_event(
                session,
                Event(
                    id=Event.new_id(),
                    invocation_id=f"emergency-delete-{uuid4().hex}",
                    author="system",
                    timestamp=time.time(),
                    actions=EventActions(
                        state_delta={EMERGENCY_CONVERSATION_ID: None}
                    ),
                ),
            )
        await self._session_service.delete_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )
        return True

    async def rename_conversation(
        self, *, uid: str, session_id: str, label: str
    ) -> bool:
        """Her own rename (issue #73): writes the literal text she typed
        to the Conversation's session state with source ``"user"`` — it
        overwrites any derived label and suppresses every later
        derivation. Returns whether the Conversation existed (``False`` →
        the caller renders 404, never leaking another user's session id).
        """
        session = await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )
        if session is None:
            return False
        await self._session_service.append_event(
            session,
            Event(
                id=Event.new_id(),
                invocation_id=f"rename-{uuid4().hex}",
                author="user",
                timestamp=time.time(),
                actions=EventActions(state_delta=dict(rename_state_delta(label))),
            ),
        )
        return True

    async def maybe_generate_title(
        self, *, uid: str, session_id: str, user_text: str, reply_text: str
    ) -> None:
        """The one-time, best-effort LLM Conversation title (spec
        2026-09-05-llm-conversation-titles): fired by ``/api/chat`` as a
        background task after her first reply has already streamed to
        the client, so it can never add latency to her turn.

        A cosmetic feature that fails invisibly: no title configured, an
        already-attempted Conversation, a session that vanished
        underneath it, or any error along the way all just return with
        no write — the existing claims-based label (``app.labels``)
        remains the fallback exactly as it does today.
        """
        if self._title_model is None:
            return
        try:
            session = await self._session_service.get_session(
                app_name=APP_NAME, user_id=uid, session_id=session_id
            )
            if session is None or session.state.get(
                CONVERSATION_TITLE_LLM_ATTEMPTED
            ):
                return
            title = await generate_title(
                user_text=user_text,
                reply_text=reply_text,
                call_model=self._title_model,
            )
            await self._session_service.append_event(
                session,
                Event(
                    id=Event.new_id(),
                    invocation_id=f"title-{uuid4().hex}",
                    author="system",
                    timestamp=time.time(),
                    actions=EventActions(
                        state_delta=llm_title_state_delta(session.state, title)
                    ),
                ),
            )
        except Exception:
            logger.exception("maybe_generate_title failed")

    async def _most_recent_session(self, *, uid: str) -> Session | None:
        """The uid's most-recently-updated session, or None with no
        sessions yet.

        Used only by the ``_case_for_country`` fallback below, for a
        ``BaseSessionService`` with no ``get_user_state`` seam. A real
        (Firestore) backend never calls this — the Case moved to
        user-scoped state (ADR-0008), so there is no longer a meaningful
        "her session" to find for it.
        """
        response = await self._session_service.list_sessions(
            app_name=APP_NAME, user_id=uid
        )
        sessions = list(response.sessions or [])
        if not sessions:
            return None
        return max(sessions, key=lambda session: session.last_update_time)

    async def _user_state(self, *, uid: str) -> dict:
        """Her raw ``adkUserState`` dict (unprefixed keys), or ``{}`` for a
        backend with no user-scoped read seam. Never gates anything."""
        try:
            return await self._session_service.get_user_state(
                app_name=APP_NAME, user_id=uid
            )
        except NotImplementedError:
            return {}

    async def _case_for_country(self, *, uid: str) -> dict | None:
        """Best-effort Case read for country resolution ONLY (ADR-0008's
        "plain GET seam" — the Case is no longer owned by a turn, so it
        must be readable without sending a message or finding a session).
        Never gates anything on this succeeding; callers already wrap it
        in their own try/except.
        """
        try:
            user_state = await self._session_service.get_user_state(
                app_name=APP_NAME, user_id=uid
            )
            return user_state.get(CASE_RAW)
        except NotImplementedError:
            # A BaseSessionService with no user-scoped read seam: fall
            # back to whatever her most-recently-touched session shows.
            session = await self._most_recent_session(uid=uid)
            return session.state.get(CASE) if session else None

    async def _open_or_reopen_emergency_conversation(
        self,
        *,
        uid: str,
        source_session_id: str | None,
        reason_category: str,
        summary: str,
        case: dict | None,
    ) -> tuple[str, dict, bool]:
        """Opens THE Emergency Conversation, or reopens the live one
        (ADR-0009: at most one at a time).

        A user-scoped pointer names the live Emergency Conversation. If it
        is still latched, this reopens it with no writes — a second press
        can never fragment her account across two rows. Otherwise a fresh
        Conversation is created carrying its Escalation Handoff, latch,
        and the pointer, all in one ``create_session`` (the state split
        routes the ``user:`` pointer to ``adkUserState`` and the rest to
        the session document). Zero model calls.

        Returns ``(emergency_session_id, case, created)`` — ``created`` is
        False when an existing live Conversation was reopened, so the
        caller can skip the proactive opener on a second press.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        pointer = (await self._user_state(uid=uid)).get(
            EMERGENCY_CONVERSATION_ID_RAW
        )
        if pointer:
            existing = await self._session_service.get_session(
                app_name=APP_NAME, user_id=uid, session_id=pointer
            )
            if existing is not None and is_emergency_conversation(existing.state):
                return pointer, (existing.state.get(CASE) or case or {}), False

        sid = uuid4().hex
        handoff = build_handoff(
            case=case,
            source_session_id=source_session_id,
            reason_category=reason_category,
            summary=summary,
        )
        new_session = await self._session_service.create_session(
            app_name=APP_NAME,
            user_id=uid,
            session_id=sid,
            state={
                EMERGENCY_LATCH: open_latch(now=now_iso),
                EMERGENCY_RESUME: empty_resume(),
                ESCALATION_HANDOFF: handoff,
                EMERGENCY_CONVERSATION_ID: sid,
                # issue #73/#89: this marker keeps the Emergency
                # Conversation's rail label a neutral date forever — a
                # topic label derived from her (shared) Case claims would
                # be a disclosure to whoever picks up the phone.
                EMERGENCY_CONVERSATION: True,
            },
        )
        return sid, (new_session.state.get(CASE) or case or {}), True

    async def press_emergency_button(self, *, uid: str) -> AsyncIterator[str]:
        """The hardcoded EMERGENCY button: renders the cached action card
        with ZERO model calls, UNCONDITIONALLY — first, before anything
        else runs, and never gated on the session store succeeding (PRD
        #34 user story 28: "help survives a dead model, a dead session
        store, or a dead connection"). The card carries the HELP_REQUESTED
        reason line — a healthy press is not a service outage, so it must
        not tell her the app is broken.

        Then it opens (or reopens) her Emergency Conversation (ADR-0009),
        still with zero model calls — the latch belongs to that
        Conversation now, so DISPATCHER honours it there starting from her
        next message. If the session store is down, that failure is
        surfaced but never retracts the card she already has.

        The ``emergency_latch`` line reports ``created`` — the frontend
        calls ``/api/emergency/opener`` (spec 2026-09-06) only when it is
        True, so a second press reopens without re-greeting.
        """
        case: dict | None = None
        try:
            case = await self._case_for_country(uid=uid)
            country = resolve_case_country(case)
        except Exception:
            logger.exception("press_emergency_button: could not read country")
            country = Country.UNKNOWN
        yield _line(
            {
                "type": "card",
                "card": cached_card(
                    country,
                    imminent_danger=True,
                    reason=SafeFloorReason.HELP_REQUESTED,
                ),
            }
        )

        try:
            flags = (case or {}).get("safety_flags") or {}
            acute = set(flags) & ACUTE_SAFETY_FLAGS
            reason = reason_category_for(flags) if acute else REASON_BUTTON
            session_id, updated_case, created = (
                await self._open_or_reopen_emergency_conversation(
                    uid=uid,
                    source_session_id=None,
                    reason_category=reason,
                    summary=button_summary((case or {}).get("language")),
                    case=case,
                )
            )
        except Exception:
            logger.exception(
                "press_emergency_button: could not open the Emergency Conversation"
            )
            yield _line({"type": "error", "detail": "session store unavailable"})
            return
        yield _line(
            {
                "type": "emergency_latch",
                "active": True,
                "session_id": session_id,
                # The proactive opener (spec 2026-09-06) fires only on a
                # fresh Conversation; a second press reopens and must not
                # re-greet.
                "created": created,
            }
        )
        yield _line(
            {"type": "case", "case": updated_case or {}, "session_id": session_id}
        )

    async def _live_emergency_session(self, *, uid: str) -> Session | None:
        """The user's one live Emergency Conversation (ADR-0009), or None.
        Same user-scoped pointer ``_open_or_reopen_emergency_conversation``
        uses; None once ``mark_safe`` has cleared the latch and pointer."""
        pointer = (await self._user_state(uid=uid)).get(
            EMERGENCY_CONVERSATION_ID_RAW
        )
        if not pointer:
            return None
        session = await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=pointer
        )
        if session is None or not is_emergency_conversation(session.state):
            return None
        return session

    async def has_live_emergency_conversation(self, *, uid: str) -> bool:
        return (await self._live_emergency_session(uid=uid)) is not None

    async def stream_emergency_opener(
        self, *, uid: str
    ) -> AsyncIterator[str]:
        """The proactive opener (spec 2026-09-06). After the button has
        rendered its card and opened the Emergency Conversation, this
        drives ONE Runner turn with the fixed ``EMERGENCY_OPENER_TRIGGER``
        stage direction: the latch is active, so DISPATCHER transfers to
        EMERGENCY, which greets her and offers the one triage choice.

        Best-effort. Any failure is logged and swallowed — the stream just
        ends with no ``reply`` line, and she still has the card and the
        Conversation. Yields nothing at all when no Emergency Conversation
        is live (the route has already 404'd in that case).
        """
        session = await self._live_emergency_session(uid=uid)
        if session is None:
            return
        language = (session.state.get(CASE) or {}).get("language")
        reply_parts: list[str] = []
        trail_calls_seen: set[str] = set()
        try:
            async for event in self._runner.run_async(
                user_id=uid,
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=EMERGENCY_OPENER_TRIGGER)],
                ),
            ):
                if event.partial or not event.content or not event.content.parts:
                    continue
                for call in event.get_function_calls():
                    if call.name in trail_calls_seen:
                        continue
                    label = progress_trail_label_for(call.name, language)
                    if label is None:
                        continue
                    trail_calls_seen.add(call.name)
                    yield _line(
                        {
                            "type": "trail",
                            "text": label,
                            "session_id": session.id,
                        }
                    )
                if event.author == "EMERGENCY":
                    reply_parts.extend(visible_texts(event.content.parts))
        except Exception:
            logger.exception("stream_emergency_opener: opener turn failed")
            return
        text = "".join(reply_parts).strip()
        if text:
            yield _line(
                {"type": "reply", "text": text, "session_id": session.id}
            )

    async def escalate_from_prompt(
        self, *, uid: str, source_session_id: str
    ) -> dict | None:
        """Confirming an Escalation Prompt (ADR-0009): opens (or reopens)
        her Emergency Conversation carrying an Escalation Handoff derived
        from the source Conversation's Case — country, reason category, a
        one-line code-owned summary, the source id. NEVER the transcript,
        and it never writes to the source Conversation, which is left
        exactly as it was.

        Returns ``{"emergency_session_id", "case"}``, or ``None`` when the
        source Conversation does not exist or belongs to another user (the
        caller renders 404, matching ``/api/chat``).
        """
        source = await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=source_session_id
        )
        if source is None:
            return None
        case = source.state.get(CASE) or {}
        reason = reason_category_for(case.get("safety_flags") or {})
        session_id, updated_case, _created = (
            await self._open_or_reopen_emergency_conversation(
                uid=uid,
                source_session_id=source_session_id,
                reason_category=reason,
                summary=disclosure_summary(reason, case.get("language")),
                case=case,
            )
        )
        return {"emergency_session_id": session_id, "case": updated_case or {}}

    async def apply_mark_safe(self, *, uid: str) -> dict:
        """Clears the Imminent Danger latch on the ONE live Emergency
        Conversation (ADR-0009) — never a Safety Flag, which this path
        cannot even reach (flags live on the user Case). The per-user
        nonce still identifies her with no Conversation id from the UI:
        the user-scoped pointer names the single unambiguous target.

        A coerced tap must not erase the disclosure, so this only flips
        the latch off (timestamped) and clears the pointer, in one event
        against that Conversation. Returns her Case, untouched.
        """
        user_state = await self._user_state(uid=uid)
        pointer = user_state.get(EMERGENCY_CONVERSATION_ID_RAW)
        case: dict = {}
        if pointer:
            session = await self._session_service.get_session(
                app_name=APP_NAME, user_id=uid, session_id=pointer
            )
            if session is not None:
                case = session.state.get(CASE) or {}
                now_iso = datetime.now(timezone.utc).isoformat()
                await self._session_service.append_event(
                    session,
                    Event(
                        id=Event.new_id(),
                        invocation_id=f"mark-safe-{uuid4().hex}",
                        author="system",
                        timestamp=time.time(),
                        actions=EventActions(
                            state_delta={
                                EMERGENCY_LATCH: clear_latch(
                                    session.state.get(EMERGENCY_LATCH),
                                    now=now_iso,
                                ),
                                EMERGENCY_CONVERSATION_ID: None,
                            }
                        ),
                    ),
                )
        if not case:
            try:
                case = await self._case_for_country(uid=uid) or {}
            except Exception:
                case = {}
        return case

    async def correct_case(
        self, *, uid: str, session_id: str, field: str, value: str
    ) -> dict | None:
        """One-tap correction (issue #44): a ``user``-sourced claim.

        Merged with ``source="user"`` so it wins outright, sets
        ``user_confirmed``, and resolves any Conflict a prior turn raised
        on this field — never silently reverted by a later extraction or
        document (``merge_case``'s merge policy). Persisted the same way a
        DISPATCHER turn persists its own state delta: one ``Event``
        carrying the mutation (ADR-0008) on a ``temp:`` key, plus the
        pre-merged Case for this turn's own immediate read, appended
        through the same session service the conversation spine uses.

        This still targets the specific ``session_id`` the UI is showing
        her — not "the" most recent session for the uid — matching
        ``/api/chat``'s own per-session contract: unlike the button/
        mark_safe above, a correction is scoped to an authenticated,
        already-open Conversation, so there is a real session to check
        ownership against (and 404 on a mismatch), even though the Case
        it writes is shared with every other Conversation she has.

        Returns the updated Case, or ``None`` when the session does not
        exist (or belongs to a different user — the caller renders 404,
        matching ``/api/chat``'s session lookup).
        """
        session = await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )
        if session is None:
            return None
        now_wall = time.time()
        now_iso = datetime.fromtimestamp(now_wall, timezone.utc).isoformat()
        delta = {"claims": {field: {"value": value, "confidence": "high"}}}
        updated_case = merge_case(
            session.state.get(CASE), delta, source="user", now=now_iso
        )
        await self._session_service.append_event(
            session,
            Event(
                id=Event.new_id(),
                invocation_id=f"correction-{uuid4().hex}",
                author="user",
                timestamp=now_wall,
                actions=EventActions(
                    state_delta={
                        CASE: updated_case,
                        CASE_MUTATIONS: [
                            {
                                "op": "merge",
                                "delta": delta,
                                "source": "user",
                                "now": now_iso,
                            }
                        ],
                    }
                ),
            ),
        )
        # Reconcile to whatever append_event actually persisted (a
        # concurrent write may have been folded in).
        return session.state.get(CASE) or updated_case

    async def stream_turn(
        self, *, uid: str, session: Session, text: str
    ) -> AsyncIterator[str]:
        """Yields the NDJSON lines of one turn: ack, trail, reply, case."""
        case = session.state.get(CASE) or {}
        language = case.get("language")
        # ADR-0009: the Escalation Prompt fires when THIS turn records a
        # NEW Pending Escalation — merge_case is the single decider of
        # "a new acute flag was disclosed" (it is add-only, so a flag is
        # only ever new once; a declined prompt needs no bookkeeping).
        # Snapshot it before the Runner (which runs extraction +
        # merge_case in the before-agent callback) so a genuinely-new
        # record is a change, not a re-fire.
        pre_pending = case.get("pending_escalation")
        # The acknowledgement is fixed and yielded before the Runner — and
        # therefore any model — is invoked.
        yield _line(
            {
                "type": "ack",
                "text": acknowledgement_for(language),
                "session_id": session.id,
            }
        )
        # The Progress Trail's opening line (issue #75, ADR-0010) fires
        # right here, immediately after the acknowledgement and still
        # before the Runner runs: reasoning and extraction happen before
        # any tool call, so a call-triggered trail would leave this exact
        # moment silent. It must not repeat the acknowledgement's own
        # wording ("reading what you wrote") — it is the next beat.
        yield _line(
            {
                "type": "trail",
                "text": progress_trail_opening_for(language),
                "session_id": session.id,
            }
        )

        reply_parts: list[str] = []
        cards: list[dict] = []
        verdicts: list[dict] = []
        proof_gaps: list[dict] = []
        regeneration_failed = False
        complaint_drafts: list[dict] = []
        recourse_routes: list[dict] = []
        # Progress Trail dedup (ADR-0010: "each specialist that runs
        # produces exactly one line"): a call name renders at most once
        # per turn even if a specialist is invoked more than once (e.g. a
        # regeneration retry).
        trail_calls_seen: set[str] = set()
        try:
            async for event in self._runner.run_async(
                user_id=uid,
                session_id=session.id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text=text)]
                ),
            ):
                if event.partial or not event.content or not event.content.parts:
                    continue
                # Progress Trail labels come from the CALL, not the
                # result (ADR-0010), so they appear while the work is
                # happening rather than after it — read live, here,
                # rather than batched with the cards/reply below. A call
                # whose name has no entry in the fixed table (e.g. an
                # internal sequencing step, a contact-directory lookup,
                # or a tool ROUTING_GUARD later refuses) renders nothing.
                for call in event.get_function_calls():
                    if call.name in trail_calls_seen:
                        continue
                    label = progress_trail_label_for(call.name, language)
                    if label is None:
                        continue
                    trail_calls_seen.add(call.name)
                    yield _line(
                        {
                            "type": "trail",
                            "text": label,
                            "session_id": session.id,
                        }
                    )
                # Tool results carrying a card render outside the LLM text
                # (ADR-0002): the card is fixed data, DISPATCHER only frames it.
                for function_response in event.get_function_responses():
                    response = function_response.response
                    cards.extend(cards_in(response))
                    if not isinstance(response, dict):
                        continue
                    # search_corpus results — already guard-filtered by
                    # ROUTING_GUARD's after-tool rail — are the code-owned
                    # verdicts payload the UI renders (ADR-0002).
                    if function_response.name == "search_corpus" and isinstance(
                        response.get("verdicts"), list
                    ):
                        verdicts.extend(response["verdicts"])
                    # PROOF_BUILDER results are the schema-validated
                    # ProofGap dict (output_schema): the scope-limit
                    # Literal guarantees the line is present, so the gap
                    # analysis the UI renders carries it verbatim. An
                    # invalid output never validates and never crosses.
                    if function_response.name == "PROOF_BUILDER" and isinstance(
                        response.get("scope_limit"), str
                    ):
                        proof_gaps.append(response)
                    # FILING_SEQUENCER's own structured answer (issue #43,
                    # ADR-0006): a failed regeneration must ship the Safe
                    # Floor PLUS an action card, guaranteed in code rather
                    # than left to DISPATCHER remembering to call
                    # action_card itself.
                    if function_response.name == "FILING_SEQUENCER" and response.get(
                        "regeneration_failed"
                    ):
                        regeneration_failed = True
                    # COMPLAINT_DRAFTER results are the schema-validated
                    # ComplaintDraftOut dict (output_schema): exactly one
                    # of draft / illegal_recruitment_refusal /
                    # premature_filing_refusal is present, never more than
                    # one and never none — the UI renders whichever the
                    # specialist actually returned, verbatim.
                    if function_response.name == "COMPLAINT_DRAFTER" and any(
                        response.get(key) is not None
                        for key in (
                            "draft",
                            "illegal_recruitment_refusal",
                            "premature_filing_refusal",
                        )
                    ):
                        complaint_drafts.append(response)
                    # RECOURSE_ROUTER's own structured answer (issue #48):
                    # its output_schema guarantees "routes" is a list (may
                    # be empty in principle, though every fork this corpus
                    # covers returns at least one) — the UI renders the
                    # typed payload directly, never framed as prose the
                    # voice composed itself (ADR-0002 seam).
                    if function_response.name == "RECOURSE_ROUTER" and isinstance(
                        response.get("routes"), (list, tuple)
                    ):
                        recourse_routes.append(response)
                # DISPATCHER is the only voice in normal turns; EMERGENCY
                # (issue #41) is the sole exception — the only other agent
                # whose text is her reply, since a transfer hands the
                # conversation to it, not DISPATCHER.
                if event.author in ("DISPATCHER", "EMERGENCY"):
                    # issue #76: model thinking arrives as parts marked
                    # ``thought=True`` INSIDE the same event content as the
                    # reply; visible_texts drops them so her raw reasoning
                    # never splices into the reply (in English, mid-crisis).
                    reply_parts.extend(visible_texts(event.content.parts))
        except Exception:
            logger.exception("DISPATCHER turn failed")
            # The hard fallback: her country's cached Safe Floor card,
            # rendered with zero further model calls — surfaced, not
            # swallowed (the error line still follows).
            yield _line(
                {
                    "type": "card",
                    "card": cached_card(
                        resolve_case_country(case),
                        imminent_danger=is_emergency_conversation(session.state),
                    ),
                    "session_id": session.id,
                }
            )
            yield _line({"type": "error", "session_id": session.id})
            return

        for card in cards:
            yield _line(
                {"type": "card", "card": card, "session_id": session.id}
            )

        updated = await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        updated_case = (updated.state.get(CASE) if updated else None) or {}
        updated_state = updated.state if updated else session.state
        in_emergency = is_emergency_conversation(updated_state)

        # The Conversation label (issue #73, ADR-0008): derived once, from
        # Case claims only, at the end of the first turn where an
        # identifiable topic fires — then it sticks. Written to the
        # session's own state so listing the rail loads no per-Conversation
        # state. Never from a Safety Flag; her rename always wins.
        if updated is not None:
            label_delta = label_state_delta(updated.state, updated_case)
            if label_delta is not None:
                await self._session_service.append_event(
                    updated,
                    Event(
                        id=Event.new_id(),
                        invocation_id=f"label-{uuid4().hex}",
                        author="system",
                        timestamp=time.time(),
                        actions=EventActions(state_delta=dict(label_delta)),
                    ),
                )

        # An inactive Plan (issue #43, ADR-0006 — an input-hash mismatch
        # detected by pure code every turn, never DISPATCHER's judgement)
        # gets the Safe Floor rendered here, unconditionally, unless a
        # plan/safe_floor/held_refusal card already streamed above this
        # turn (e.g. DISPATCHER regenerated a replacement itself).
        plan_inactive = bool(updated) and updated.state.get(PLAN_ACTIVE) is False
        already_shown = any(
            card.get("type") in _PLAN_STATUS_CARD_TYPES for card in cards
        )
        if plan_inactive and not already_shown:
            yield _line(
                {
                    "type": "card",
                    "card": build_card(
                        resolve_case_country(updated_case),
                        reason=SafeFloorReason.FACTS_CHANGED,
                        imminent_danger=in_emergency,
                    ),
                    "session_id": session.id,
                }
            )

        # ADR-0006: a failed regeneration ships the Safe Floor PLUS an
        # action card — guaranteed here in code (not just DISPATCHER's
        # instruction) unless DISPATCHER already rendered one itself.
        if regeneration_failed and not any(
            card.get("type") == "action_card" for card in cards
        ):
            yield _line(
                {
                    "type": "card",
                    "card": _default_action_card(resolve_case_country(updated_case)),
                    "session_id": session.id,
                }
            )

        # ADR-0009: a NEW Pending Escalation recorded this turn shows the
        # Escalation Prompt — the Safe Floor card rendered at the SAME
        # time and unconditionally (the card comes WITH the prompt, not
        # after it, so the number she needs is on screen whether or not
        # she taps), plus a two-tap offer to open an Emergency
        # Conversation. It transfers nobody: not in an Emergency
        # Conversation already, and DISPATCHER's instruction only
        # transfers on the latch, which a disclosure never sets.
        new_pending = updated_case.get("pending_escalation")
        if (
            isinstance(new_pending, dict)
            and new_pending != pre_pending
            and not in_emergency
        ):
            escalation_reason = reason_category_for(
                updated_case.get("safety_flags") or {}
            )
            yield _line(
                {
                    "type": "card",
                    "card": build_card(
                        resolve_case_country(updated_case),
                        reason=SafeFloorReason.ACUTE_DISCLOSURE,
                        imminent_danger=True,
                    ),
                    "session_id": session.id,
                }
            )
            yield _line(
                {
                    "type": "escalation_prompt",
                    "escalation_prompt": {
                        "reason_category": escalation_reason,
                        "source_session_id": session.id,
                        "country": resolve_case_country(updated_case).value,
                    },
                    "session_id": session.id,
                }
            )

        yield _line(
            {
                "type": "reply",
                "text": "".join(reply_parts),
                "session_id": session.id,
            }
        )

        if verdicts:
            yield _line(
                {
                    "type": "verdicts",
                    "verdicts": verdicts,
                    "session_id": session.id,
                }
            )

        for gap in proof_gaps:
            yield _line(
                {
                    "type": "proof_gap",
                    "proof_gap": gap,
                    "session_id": session.id,
                }
            )

        for draft in complaint_drafts:
            yield _line(
                {
                    "type": "complaint_draft",
                    "complaint_draft": draft,
                    "session_id": session.id,
                }
            )

        for recourse in recourse_routes:
            yield _line(
                {
                    "type": "recourse_routes",
                    "recourse_routes": recourse,
                    "session_id": session.id,
                }
            )

        # ADR-0009: the latch is Conversation state now — the client keys
        # the "I'm safe" control off THIS line, per Conversation, not off
        # a user-wide Case flag. Emitted only for the Emergency
        # Conversation, so an ordinary turn's stream shape is unchanged;
        # ``mark_safe``'s own response clears the control on the client.
        if in_emergency:
            yield _line(
                {
                    "type": "emergency_latch",
                    "active": True,
                    "session_id": session.id,
                }
            )

        yield _line(
            {
                "type": "case",
                "case": updated_case,
                "session_id": session.id,
            }
        )
