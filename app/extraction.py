"""read_narrative: the typed extraction call that produces a CaseDelta.

A plain function (PRD #34): one typed Gemini call with a response schema,
invoked from the root agent's before-agent callback — strictly before the
DISPATCHER turn, never parallel with it. It fails closed: an unparseable
response, a timeout, a 429, or a safety block returns ``None`` (the Case
stays unchanged) and never raises into the turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal, Optional

from google.adk.models import BaseLlm, LlmRequest
from google.genai import types
from pydantic import BaseModel

from app.case import SAFETY_FLAGS

logger = logging.getLogger(__name__)

EXTRACTION_TIMEOUT_SECONDS = 15.0

Language = Literal["en", "tl", "taglish", "ceb", "other"]
Confidence = Literal["high", "medium", "low"]

SafetyFlag = Literal[
    "PHYSICAL_ASSAULT_ONGOING",
    "PHYSICAL_ASSAULT_PAST",
    "THREAT_OF_HARM",
    "CONFINED",
    "PASSPORT_WITHHELD",
]


class ClaimField(BaseModel):
    value: str
    confidence: Confidence = "medium"


class NarrativeClaims(BaseModel):
    """Closed set of fields extraction may assert; all optional."""

    country: Optional[ClaimField] = None
    location_now: Optional[ClaimField] = None
    employer_name: Optional[ClaimField] = None
    agency_name: Optional[ClaimField] = None
    job_role: Optional[ClaimField] = None
    monthly_salary: Optional[ClaimField] = None
    months_unpaid: Optional[ClaimField] = None
    tenure_months: Optional[ClaimField] = None
    contract_available: Optional[ClaimField] = None
    passport_location: Optional[ClaimField] = None


class CaseDelta(BaseModel):
    """What one turn's narrative adds to the Case, plus detected language."""

    language: Language
    claims: NarrativeClaims = NarrativeClaims()
    safety_flags: list[SafetyFlag] = []


_EXTRACTOR_INSTRUCTION = """\
You extract structured facts from one message written by a Filipino overseas
worker who may be in distress. The message may be in English, Tagalog,
Taglish (mixed Tagalog and English), Cebuano/Bisaya, or another Philippine
language.

Return ONLY the fields the message itself supports. Never guess or infer a
value the writer did not state. Numeric fields are decimal strings.

language: the language of THIS message — "en" when it is written in
English, even if it names Filipino people, places, employers, or
agencies (a proper noun is not a Tagalog word); "tl" for Tagalog/Filipino;
"taglish" only when an actual Tagalog/Filipino word is mixed into an
otherwise English message, not merely an English message about a
Filipino worker; "ceb" for Cebuano/Bisaya; "other" for any other
language. Default to "en" when in doubt — never "tl" or "taglish" for a
message with no actual Tagalog words in it.

safety_flags: only when the message states it. Tagalog verb aspect matters:
"sinasaktan/sinasaktan niya ako" (ongoing) -> PHYSICAL_ASSAULT_ONGOING;
"sinaktan" (completed) -> PHYSICAL_ASSAULT_PAST; "sasaktan" (threatened)
-> THREAT_OF_HARM. Confinement ("hindi ako makalabas", locked in) ->
CONFINED. Employer holding the passport -> PASSPORT_WITHHELD.
"""


def _delta_to_dict(delta: CaseDelta) -> dict:
    claims = {
        field: {"value": claim.value, "confidence": claim.confidence}
        for field, claim in delta.claims
        if claim is not None
    }
    flags = [flag for flag in delta.safety_flags if flag in SAFETY_FLAGS]
    return {"language": delta.language, "claims": claims, "safety_flags": flags}


async def read_narrative(
    *,
    llm: BaseLlm,
    text: str,
    timeout: float = EXTRACTION_TIMEOUT_SECONDS,
) -> dict | None:
    """Runs the typed extraction call; returns a CaseDelta dict or None.

    Fails closed on every failure mode — timeout, transport error (429),
    safety block (no candidate text), unparseable or schema-invalid JSON —
    by returning None so the caller leaves the Case unchanged. Never raises.
    """
    request = LlmRequest(
        model=llm.model,
        contents=[types.Content(role="user", parts=[types.Part(text=text)])],
        config=types.GenerateContentConfig(
            system_instruction=_EXTRACTOR_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=CaseDelta,
            temperature=0.0,
        ),
    )
    try:
        async with asyncio.timeout(timeout):
            response = None
            async for chunk in llm.generate_content_async(request, stream=False):
                response = chunk
        payload = json.loads(response.content.parts[0].text)
        delta = CaseDelta.model_validate(payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("read_narrative failed closed; Case left unchanged")
        return None
    return _delta_to_dict(delta)
