"""Model-pinned Taglish verb-aspect fixture suite (issue #41, PRD #34).

Confirms the real Gemini model actually discriminates Tagalog assault-verb
aspect the way ``_EXTRACTOR_INSTRUCTION`` claims it does:

* "sinaktan" (completed)      -> PHYSICAL_ASSAULT_PAST    (not acute)
* "sinasaktan" (ongoing)      -> PHYSICAL_ASSAULT_ONGOING  (acute)
* "sasaktan niya ako" (threat) -> THREAT_OF_HARM            (acute)

This makes a real network call to the pinned model in ``GEMINI_MODEL`` and
is deliberately NOT part of default CI: it is gated behind ``GEMINI_API_KEY``
(same pattern as tests/test_firestore_session_service.py's emulator gate)
and is meant to be run by hand whenever the extractor prompt or the pinned
model string changes — not on every commit, since it costs real API calls
and is not fully deterministic.
"""

import asyncio
import os

import pytest
from google import genai
from google.adk.models import Gemini

from app.agent import GEMINI_MODEL
from app.case import ACUTE_SAFETY_FLAGS
from app.extraction import read_narrative

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="requires a real GEMINI_API_KEY; run by hand on extractor/model changes",
)


@pytest.fixture()
def llm():
    return Gemini(model=GEMINI_MODEL, client=genai.Client(api_key=os.environ["GEMINI_API_KEY"]))


class TestVerbAspectDiscrimination:
    """Pinned to GEMINI_MODEL exactly as agent.py wires it — not a fake."""

    def test_completed_past_assault_is_not_acute(self, llm):
        delta = asyncio.run(
            read_narrative(llm=llm, text="Sinaktan ako ng amo ko noong isang linggo.")
        )
        assert delta is not None
        assert "PHYSICAL_ASSAULT_PAST" in delta["safety_flags"]
        assert not (ACUTE_SAFETY_FLAGS & set(delta["safety_flags"]))

    def test_ongoing_assault_is_acute(self, llm):
        delta = asyncio.run(
            read_narrative(llm=llm, text="Sinasaktan ako ng amo ko ngayon.")
        )
        assert delta is not None
        assert "PHYSICAL_ASSAULT_ONGOING" in delta["safety_flags"]
        assert ACUTE_SAFETY_FLAGS & set(delta["safety_flags"])

    def test_stated_threat_is_acute(self, llm):
        delta = asyncio.run(
            read_narrative(llm=llm, text="Sasaktan niya ako kapag umuwi siya.")
        )
        assert delta is not None
        assert "THREAT_OF_HARM" in delta["safety_flags"]
        assert ACUTE_SAFETY_FLAGS & set(delta["safety_flags"])
