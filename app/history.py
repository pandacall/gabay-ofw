"""Turning a stored Conversation back into stream lines (issue #72, ADR-0008).

Re-opening a Conversation needs its past transcript, which nothing
returned before: ``/api/chat`` only ever streamed a turn as it happened
and the client kept the lines in memory. ``replay_conversation`` reads a
Conversation's stored ADK events and re-emits the same NDJSON line types
that ``app.chat.ChatService.stream_turn`` produces live — ``user``,
``reply``, ``card`` and the typed finding lines — so the client renders a
re-opened Conversation through the identical ``handleChatLine`` path.

Two line types are deliberately NOT reproduced: the per-turn ``ack`` and
the Progress Trail ``trail`` lines (ADR-0010) are transient scaffolding
for a turn in flight, not part of what she said or what Gabay answered.

Cards carrying deadlines do not replay as themselves. A Plan card seen in
a past turn still contains ``expires_at`` values the one live Plan
(ADR-0008) may since have replaced; replayed verbatim it would be an
"expired deadline she acts on" (ADR-0006) reached simply by scrolling
back. Such a card collapses to a single ``stale_plan_ref`` line the
client renders as a pointer to the live Plan. Clock-free cards — contact
directories, Safe Floor cards, verdicts, proof gaps, HELD refusals —
replay unchanged.
"""

from __future__ import annotations

from google.adk.events import Event

#: Every key under a tool result whose dict value is fixed, non-model
#: data to render as a card, never framed as free text (ADR-0002).
#: ``card`` is the original convention
#: (office_directory/action_card/safe_floor_card); ``held_refusal`` and
#: ``plan`` are FILING_SEQUENCER's own result shapes (issue #42) — a
#: HELD-jurisdiction refusal and a verified Plan, each already typed as
#: its own ``"type"`` for the UI to render directly.
_CARD_KEYS = ("card", "held_refusal", "plan")

#: Card ``type`` values that carry per-step deadlines and therefore must
#: never replay as actionable in a past turn (ADR-0008 / ADR-0006). Only
#: the verified Plan card does; every other card the agent layer renders
#: is clock-free.
_DEADLINE_CARD_TYPES = frozenset({"plan"})


def cards_in(response: object) -> list[dict]:
    """Every card-shaped value in one tool-call result, in a fixed key
    order. A verified Plan carries no ``"type"`` of its own (ADR-0006's
    Plan shape), so one is added here rather than by the caller. A
    regenerated plan's ``delta`` / ``was_stale`` (issue #43) ride
    alongside it on the SAME response dict, never nested inside the plan
    itself — they are folded onto the rendered card here.

    Lives here rather than in ``app.chat`` so both the live stream and
    the re-open replay (``replay_conversation``) share one card-shaping
    rule without a circular import.
    """
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


def replay_conversation(events: list[Event]) -> list[dict]:
    """The stored ``events`` of one Conversation as replayable stream lines.

    Order follows the events themselves, which is the live order: a user
    line, then any findings that turn's tools produced, then Gabay's
    reply framing them.
    """
    lines: list[dict] = []
    for event in events:
        if not event.content or not event.content.parts:
            continue

        for function_response in event.get_function_responses():
            response = function_response.response
            for card in cards_in(response):
                if card.get("type") in _DEADLINE_CARD_TYPES:
                    lines.append({"type": "stale_plan_ref"})
                else:
                    lines.append({"type": "card", "card": card})
            if not isinstance(response, dict):
                continue
            if function_response.name == "search_corpus" and isinstance(
                response.get("verdicts"), list
            ):
                lines.append({"type": "verdicts", "verdicts": response["verdicts"]})
            if function_response.name == "PROOF_BUILDER" and isinstance(
                response.get("scope_limit"), str
            ):
                lines.append({"type": "proof_gap", "proof_gap": response})
            if function_response.name == "COMPLAINT_DRAFTER" and any(
                response.get(key) is not None
                for key in (
                    "draft",
                    "illegal_recruitment_refusal",
                    "premature_filing_refusal",
                )
            ):
                lines.append({"type": "complaint_draft", "complaint_draft": response})
            if function_response.name == "RECOURSE_ROUTER" and isinstance(
                response.get("routes"), (list, tuple)
            ):
                lines.append({"type": "recourse_routes", "recourse_routes": response})

        texts = [part.text for part in event.content.parts if part.text]
        if not texts:
            continue
        if event.author == "user":
            lines.append({"type": "user", "text": "".join(texts)})
        elif event.author in ("DISPATCHER", "EMERGENCY"):
            lines.append({"type": "reply", "text": "".join(texts)})

    return lines
