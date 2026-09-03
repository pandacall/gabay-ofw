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
voice composed itself.

``ChatService.correct_case`` (issue #44) is the one-tap correction seam:
the Case streamed on the ``case`` line is rendered and correctable by the
UI directly (never only narrated by DISPATCHER's prose), and a tap there
calls this method instead of going through a conversation turn at all.
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

from app.agent import APP_NAME, acknowledgement_for, build_adk_app
from app.case import mark_safe as case_mark_safe
from app.case import merge_case
from app.case import press_emergency_button as case_press_emergency_button
from app.directory import Country, resolve_case_country, resolve_keys
from app.safe_floor import CARD_KEYS, SafeFloorReason, build_card, cached_card, is_imminent_danger

logger = logging.getLogger(__name__)


def _line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


#: Every key under a tool result whose dict value is fixed, non-model data
#: to render as a card, never framed as free text (ADR-0002). ``card`` is
#: the original convention (office_directory/action_card/safe_floor_card);
#: ``held_refusal`` and ``plan`` are FILING_SEQUENCER's own result shapes
#: (issue #42) — a HELD-jurisdiction refusal and a verified Plan, each
#: already typed as its own ``"type"`` for the UI to render directly.
_CARD_KEYS = ("card", "held_refusal", "plan")

#: Card types that already tell her the state of her Plan (or its
#: replacement, per ADR-0006) — the auto-rendered inactive-plan Safe
#: Floor (below) is skipped when one of these already streamed this turn,
#: so she never sees two contradicting cards.
_PLAN_STATUS_CARD_TYPES = frozenset({"plan", "safe_floor", "held_refusal"})


def _cards_in(response: object) -> list[dict]:
    """Every card-shaped value in one tool-call result, in a fixed key
    order. A verified Plan carries no ``"type"`` of its own (ADR-0006's
    Plan shape), so one is added here rather than by the caller. A
    regenerated plan's ``delta`` / ``was_stale`` (issue #43) ride
    alongside it on the SAME response dict, never nested inside the plan
    itself — they are folded onto the rendered card here."""
    if not isinstance(response, dict):
        return []
    found: list[dict] = []
    for key in _CARD_KEYS:
        value = response.get(key)
        if not isinstance(value, dict):
            continue
        if key != "plan":
            found.append(value)
            continue
        card = {"type": "plan", **value}
        if isinstance(response.get("delta"), dict):
            card["delta"] = response["delta"]
        if response.get("was_stale"):
            card["was_stale"] = True
        found.append(card)
    return found


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

    def __init__(self, *, session_service: BaseSessionService, llm: BaseLlm):
        self._session_service = session_service
        self._runner = Runner(
            app=build_adk_app(llm), session_service=session_service
        )

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

    async def _most_recent_session(self, *, uid: str) -> Session | None:
        """The uid's most-recently-updated session, or None with no
        sessions yet. Used by the button and mark_safe paths, which act
        on "the" session for a uid rather than one named on the request
        (a nonce is per-uid, not per-session)."""
        response = await self._session_service.list_sessions(
            app_name=APP_NAME, user_id=uid
        )
        sessions = list(response.sessions or [])
        if not sessions:
            return None
        return max(sessions, key=lambda session: session.last_update_time)

    async def _mutate_case(
        self, *, uid: str, mutate
    ) -> tuple[str, dict | None]:
        """Loads (or creates) the uid's current session, applies a pure
        Case-mutating function outside the Runner's turn flow, and
        persists the delta as a hand-built Event — the same append_event
        path a normal turn uses, without running the model at all.
        Returns ``(session_id, new_case)``."""
        session = await self._most_recent_session(uid=uid)
        if session is None:
            session = await self._session_service.create_session(
                app_name=APP_NAME, user_id=uid
            )
        now_wall = time.time()
        now_iso = datetime.fromtimestamp(now_wall, timezone.utc).isoformat()
        case = session.state.get("case")
        new_case = mutate(case, now=now_iso)
        event = Event(
            id=Event.new_id(),
            invocation_id=f"emergency-{uuid4().hex}",
            author="system",
            timestamp=now_wall,
            actions=EventActions(state_delta={"case": new_case}),
        )
        await self._session_service.append_event(session, event)
        return session.id, new_case

    async def press_emergency_button(self, *, uid: str) -> AsyncIterator[str]:
        """The hardcoded EMERGENCY button: renders the cached action card
        with ZERO model calls, UNCONDITIONALLY — first, before anything
        else runs, and never gated on the session store succeeding (PRD
        #34 user story 28: "help survives a dead model, a dead session
        store, or a dead connection"). Recording the press (Imminent
        Danger predicate on, so DISPATCHER honors it starting next turn)
        is attempted afterward as a best-effort side effect; if the
        session store is down, that failure is surfaced but never
        retracts the card she already has.
        """
        try:
            session = await self._most_recent_session(uid=uid)
            country = resolve_case_country(session.state.get("case") if session else None)
        except Exception:
            logger.exception("press_emergency_button: could not read country")
            country = Country.UNKNOWN
        yield _line(
            {"type": "card", "card": cached_card(country, imminent_danger=True)}
        )

        try:
            session_id, case = await self._mutate_case(
                uid=uid, mutate=case_press_emergency_button
            )
        except Exception:
            logger.exception("press_emergency_button: could not record the press")
            yield _line({"type": "error", "detail": "session store unavailable"})
            return
        yield _line(
            {"type": "case", "case": case or {}, "session_id": session_id}
        )

    async def apply_mark_safe(self, *, uid: str) -> dict:
        """Clears the Imminent Danger PREDICATE (never the safety flag)
        on the uid's current session. Returns the updated Case."""
        _, case = await self._mutate_case(uid=uid, mutate=case_mark_safe)
        return case or {}

    async def correct_case(
        self, *, uid: str, session_id: str, field: str, value: str
    ) -> dict | None:
        """One-tap correction (issue #44): a ``user``-sourced claim.

        Merged with ``source="user"`` so it wins outright, sets
        ``user_confirmed``, and resolves any Conflict a prior turn raised
        on this field — never silently reverted by a later extraction or
        document (``merge_case``'s merge policy). Persisted the same way a
        DISPATCHER turn persists its own state delta: one ``Event``
        carrying the new Case as a session-state delta, appended through
        the same session service the conversation spine uses.

        Unlike ``press_emergency_button``/``apply_mark_safe`` above, this
        acts on the specific ``session_id`` the UI is showing her — not
        "the" most recent session for the uid — matching ``/api/chat``'s
        own per-session contract (a correction always targets the Case
        she is looking at).

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
        updated_case = merge_case(
            session.state.get("case"),
            {"claims": {field: {"value": value, "confidence": "high"}}},
            source="user",
            now=now_iso,
        )
        await self._session_service.append_event(
            session,
            Event(
                id=Event.new_id(),
                invocation_id=f"correction-{uuid4().hex}",
                author="user",
                timestamp=now_wall,
                actions=EventActions(state_delta={"case": updated_case}),
            ),
        )
        return updated_case

    async def stream_turn(
        self, *, uid: str, session: Session, text: str
    ) -> AsyncIterator[str]:
        """Yields the NDJSON lines of one turn: ack, reply, case."""
        case = session.state.get("case") or {}
        # The acknowledgement is fixed and yielded before the Runner — and
        # therefore any model — is invoked.
        yield _line(
            {
                "type": "ack",
                "text": acknowledgement_for(case.get("language")),
                "session_id": session.id,
            }
        )

        reply_parts: list[str] = []
        cards: list[dict] = []
        verdicts: list[dict] = []
        proof_gaps: list[dict] = []
        regeneration_failed = False
        complaint_drafts: list[dict] = []
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
                # Tool results carrying a card render outside the LLM text
                # (ADR-0002): the card is fixed data, DISPATCHER only frames it.
                for function_response in event.get_function_responses():
                    response = function_response.response
                    cards.extend(_cards_in(response))
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
                # DISPATCHER is the only voice in normal turns; EMERGENCY
                # (issue #41) is the sole exception — the only other agent
                # whose text is her reply, since a transfer hands the
                # conversation to it, not DISPATCHER.
                if event.author in ("DISPATCHER", "EMERGENCY"):
                    reply_parts.extend(
                        part.text for part in event.content.parts if part.text
                    )
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
                        imminent_danger=is_imminent_danger(case),
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
        updated_case = (updated.state.get("case") if updated else None) or {}

        # An inactive Plan (issue #43, ADR-0006 — an input-hash mismatch
        # detected by pure code every turn, never DISPATCHER's judgement)
        # gets the Safe Floor rendered here, unconditionally, unless a
        # plan/safe_floor/held_refusal card already streamed above this
        # turn (e.g. DISPATCHER regenerated a replacement itself).
        plan_inactive = bool(updated) and updated.state.get("plan_active") is False
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
                        imminent_danger=is_imminent_danger(updated_case),
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

        yield _line(
            {
                "type": "case",
                "case": updated_case,
                "session_id": session.id,
            }
        )
