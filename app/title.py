"""LLM-generated Conversation titles (spec: docs/superpowers/specs/
2026-09-05-llm-conversation-titles-design.md).

Extends the closed-set claims-based label (``app.labels``) with a
richer, model-generated title, while keeping the property that made the
existing design claims-only in the first place: the title must never
leak an allegation.

Safety is deterministic, code-owned, and never a second model call —
consistent with ROUTING_GUARD's own pattern elsewhere in this codebase.
``is_title_safe`` runs in plain code after every generation attempt; a
rejection is never itself decided by asking the model whether its own
output was safe.

Attempted once per Conversation, in the background, after the first
turn: ``generate_title`` retries up to ``MAX_ATTEMPTS`` times internally
(rejections and model errors both count against the budget) and returns
``None`` — never raises — when nothing safe is produced, so the caller's
fallback is simply "write nothing" (the existing claims-based label
keeps running as it already does today).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Awaitable, Callable

from pydantic import BaseModel

from app.case import SAFETY_FLAGS

if TYPE_CHECKING:
    from google.genai import Client

#: A prompt in, generated text out. The only seam this module depends on
#: — production wires it to a direct Gemini call (not the ADK Runner);
#: tests wire it to a canned async function.
ModelCall = Callable[[str], Awaitable[str]]

#: Total attempts per Conversation, including the first: a rejection or
#: a model error both consume one, so cost/latency for this one-time
#: background task is bounded even in the worst case.
MAX_ATTEMPTS = 3

MAX_TITLE_LENGTH = 40

#: Terms tied to each closed Safety Flag (app.case.SAFETY_FLAGS) that
#: would name the allegation rather than the administrative subject —
#: e.g. "Passport and papers" is fine, "employer withheld my passport"
#: names the PASSPORT_WITHHELD flag and is blocked. Kept in lockstep
#: with the flag enum by the assertion below: a new flag added there
#: must get an entry here before this module can claim to cover it.
_PHYSICAL_ASSAULT_TERMS = (
    "assault", "assaulted", "hit me", "hitting", "beat", "beaten",
    "beating", "punch", "punched", "slap", "slapped", "attacked",
)
_SAFETY_FLAG_TERMS: dict[str, tuple[str, ...]] = {
    # Ongoing and past assault share the same term list: the words
    # naming the allegation don't depend on tense.
    "PHYSICAL_ASSAULT_ONGOING": _PHYSICAL_ASSAULT_TERMS,
    "PHYSICAL_ASSAULT_PAST": _PHYSICAL_ASSAULT_TERMS,
    "THREAT_OF_HARM": ("threat", "threatened", "threatening"),
    "CONFINED": (
        "confine", "confined", "confinement", "locked in", "locked up",
        "trapped", "imprisoned",
    ),
    "PASSPORT_WITHHELD": (
        "withheld", "withholding", "confiscat", "seized passport",
        "took my passport", "keeping my passport",
    ),
}
assert set(_SAFETY_FLAG_TERMS) == SAFETY_FLAGS, (
    "app.title's blocklist has drifted from app.case.SAFETY_FLAGS — add "
    "an entry for every flag before this module can claim to cover it"
)

#: Hard-stop terms not tied to a specific flag — never a title regardless
#: of category.
_HARD_STOP_TERMS = (
    "kill", "suicide", "rape", "raped", "blood", "hospital", "weapon",
    "gun", "knife", "molest", "abuse", "abused", "trafficking",
    "trafficked", "minor", "child abuse",
)

_BLOCKLIST = frozenset(
    term.lower()
    for terms in _SAFETY_FLAG_TERMS.values()
    for term in terms
) | frozenset(term.lower() for term in _HARD_STOP_TERMS)

_DIGIT_RE = re.compile(r"\d")

#: Common Tagalog/Cebuano function words that essentially never appear in
#: a natural English 3-6 word title (spec Decision 5: titles are always
#: English, which is what makes the English-only ``_BLOCKLIST`` above a
#: valid safety net at all). Her own message and DISPATCHER's reply — the
#: two inputs to the generation prompt — are frequently non-English by
#: design (issue #67), so this is a real path, not a hypothetical one:
#: a prompt instruction alone is never trusted for a safety-critical
#: property in this codebase (see ROUTING_GUARD), so this is the
#: deterministic backstop if the model doesn't comply. Matched on word
#: boundaries, unlike ``_BLOCKLIST``'s substring match, so short markers
#: like "mo" or "ba" don't false-positive inside English words.
_NON_ENGLISH_MARKERS = frozenset(
    {
        "ako", "ko", "mo", "niya", "namin", "natin", "kami", "tayo",
        "sila", "siya", "hindi", "wala", "akin", "amo", "ba", "po",
        "opo", "kasi", "yung", "nang", "nila", "gikuha", "gikan",
    }
)
_NON_ENGLISH_RE = re.compile(
    r"\b(" + "|".join(_NON_ENGLISH_MARKERS) + r")\b", re.IGNORECASE
)


def is_title_safe(title: str) -> bool:
    """Whether a candidate title is safe to show verbatim in the rail.

    Deterministic, no I/O, never a model call. Rejects: empty/blank,
    any digit character (current claims-based labels never show numbers
    either), over-length, a case-insensitive blocklist hit, or a
    Tagalog/Cebuano function-word marker (the blocklist above is
    English-only vocabulary, so a non-English title would otherwise
    bypass it entirely).
    """
    if not title or not title.strip():
        return False
    if len(title) > MAX_TITLE_LENGTH:
        return False
    if _DIGIT_RE.search(title):
        return False
    if _NON_ENGLISH_RE.search(title):
        return False
    lowered = title.lower()
    return not any(term in lowered for term in _BLOCKLIST)


_PROMPT_TEMPLATE = """You are naming a conversation thread in a support app, \
the way a chat app titles a conversation.

Read the exchange below and produce a short title (3-6 words) that names \
ONLY the administrative or legal category of what was discussed — for \
example the kind of labor issue (unpaid wages, passport concerns, \
contract dispute, agency conduct, job conditions), or "General inquiry" \
if nothing more specific fits.

Never include: specific incident details, numbers, dates, names, \
locations, or any wording that implies violence, confinement, threats, \
or an emergency. Describe the subject, not the allegation.

Always respond in English, even though her message and the reply below \
may be in Tagalog, Taglish, or Cebuano.

Her message: {user_text}
The assistant's reply: {reply_text}
"""

_RETRY_SUFFIX = """
Your previous attempt was too specific or touched a disallowed topic. \
Produce a more general, purely administrative title instead — do not \
repeat or rephrase your previous attempt.
"""


def _build_prompt(user_text: str, reply_text: str, *, retry: bool) -> str:
    prompt = _PROMPT_TEMPLATE.format(user_text=user_text, reply_text=reply_text)
    if retry:
        prompt += _RETRY_SUFFIX
    return prompt


class TitleOut(BaseModel):
    """The structured shape the generation call is asked for, via
    ``response_schema`` — a single field, so a malformed/empty response
    fails ``is_title_safe``'s blank check rather than needing its own
    parse-error handling."""

    title: str


def build_gemini_model_call(client: "Client", model: str) -> ModelCall:
    """The production ``ModelCall``: a direct, out-of-band call to
    Gemini via the raw ``google-genai`` client — never the ADK
    Runner/DISPATCHER, per the spec's "plain out-of-band call"
    decision. Reuses the same ``genai.Client`` and exact-pinned
    ``GEMINI_MODEL`` the ADK ``Gemini`` wrapper is already built with
    (``app.main._production_chat_service``), not a second model
    dependency.
    """

    async def call_model(prompt: str) -> str:
        from google.genai import types

        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TitleOut,
            ),
        )
        parsed = response.parsed
        if not isinstance(parsed, TitleOut):
            return ""
        return parsed.title

    return call_model


async def generate_title(
    *, user_text: str, reply_text: str, call_model: ModelCall
) -> str | None:
    """Up to ``MAX_ATTEMPTS`` tries at a safe title; ``None`` on
    exhaustion (the caller's fallback is simply "write nothing").

    A retry never echoes back the specific rejected text — only a
    generic "be more administrative" instruction — so the model can't
    just word-swap around the blocklist. A model error counts as a
    failed attempt, identically to a filter rejection.
    """
    for attempt in range(MAX_ATTEMPTS):
        prompt = _build_prompt(user_text, reply_text, retry=attempt > 0)
        try:
            candidate = await call_model(prompt)
        except Exception:
            continue
        candidate = (candidate or "").strip()
        if is_title_safe(candidate):
            return candidate
    return None
