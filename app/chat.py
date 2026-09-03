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
rendered by the UI outside the LLM text, per ADR-0002.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, Session
from google.genai import types

from app.agent import APP_NAME, acknowledgement_for, build_adk_app
from app.directory import Country, resolve_case_country
from app.safe_floor import cached_card, is_imminent_danger

logger = logging.getLogger(__name__)


def _line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


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
                    if not isinstance(response, dict):
                        continue
                    if isinstance(response.get("card"), dict):
                        cards.append(response["card"])
                    # search_corpus results — already guard-filtered by
                    # ROUTING_GUARD's after-tool rail — are the code-owned
                    # verdicts payload the UI renders (ADR-0002).
                    if function_response.name == "search_corpus" and isinstance(
                        response.get("verdicts"), list
                    ):
                        verdicts.extend(response["verdicts"])
                if event.author == "DISPATCHER":
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

        updated = await self._session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        yield _line(
            {
                "type": "case",
                "case": (updated.state.get("case") if updated else None) or {},
                "session_id": session.id,
            }
        )
