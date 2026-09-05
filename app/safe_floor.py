"""Per-country Safe Floor cards (issue #39, PRD #34).

One fixed, code-owned artifact per country. When no verified Plan can be
shown, she gets this — never an unverified sequence. Contacts are
resolved from the immutable directory and dialability-filtered; reason
lines are a fixed enum of hand-written, individually reviewed strings;
the "do not leave before speaking to the MWO" line is suppressed under
the Imminent Danger latch (``imminent_danger=True``).

Two render paths:

* **Hard fallback** — ``CACHED_CARDS`` is precomputed at import. When the
  session store or the extractor is down, the card renders from this
  cache with ZERO model calls.
* **Bounded outcome** — inside a working turn (no verified plan, HELD
  jurisdiction) DISPATCHER frames the card in its own words via the
  ``safe_floor_card`` tool; the card itself is fixed and streams to the
  UI as structured data outside the LLM text (ADR-0002's principle).

The Imminent Danger latch now lives in ``app.emergency`` (ADR-0009): it is
Conversation state — "this Conversation is the Emergency one" — set by the
EMERGENCY button or a confirmed Escalation Prompt, cleared only by
``mark_safe``, never by the clock. This module re-exports
``is_emergency_conversation`` for callers that only need the Safe Floor
surface, and keeps the ``imminent_danger`` card parameter (it only ever
meant "suppress the stay-put line").
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.case import ACUTE_SAFETY_FLAGS
from app.directory import Country, resolve_keys
from app.emergency import is_emergency_conversation

__all__ = [
    "ACUTE_SAFETY_FLAGS",
    "is_emergency_conversation",
    "SafeFloorReason",
    "REASON_LINES",
    "HOLD_LINE",
    "build_card",
    "CACHED_CARDS",
    "CACHED_REASONS",
    "cached_card",
]


# ---------------------------------------------------------------------------
# Reason lines: a fixed enum of hand-written strings.
# ---------------------------------------------------------------------------


class SafeFloorReason(str, Enum):
    NO_VERIFIED_PLAN = "NO_VERIFIED_PLAN"
    JURISDICTION_HELD = "JURISDICTION_HELD"
    SERVICE_DOWN = "SERVICE_DOWN"
    FACTS_CHANGED = "FACTS_CHANGED"
    #: A healthy press of the "I need help now" button. The button always
    #: serves a zero-model cached card; before this reason existed it
    #: reused SERVICE_DOWN and told every caller the app was broken.
    HELP_REQUESTED = "HELP_REQUESTED"
    #: Rendered WITH the Escalation Prompt (ADR-0009): she has just
    #: disclosed an acute hazard mid-conversation. The card comes with the
    #: prompt, not after it — so the number she needs is on screen whether
    #: or not she taps.
    ACUTE_DISCLOSURE = "ACUTE_DISCLOSURE"


#: Hand-written, individually reviewed. Never generated, never templated.
REASON_LINES: dict[SafeFloorReason, str] = {
    SafeFloorReason.NO_VERIFIED_PLAN: (
        "Wala pa akong verified na plano para sa sitwasyon mo, kaya hindi ako"
        " magbibigay ng hula. / I don't have a verified plan for your"
        " situation yet, so I won't guess. These offices are real and can"
        " answer for your case."
    ),
    SafeFloorReason.JURISDICTION_HELD: (
        "Hindi ko pa na-verify ang tamang pagkakasunod-sunod ng filing sa"
        " bansang ito. / I haven't verified the correct filing order for"
        " this country, so I won't invent one. The MWO can confirm it —"
        " these are their real numbers."
    ),
    SafeFloorReason.SERVICE_DOWN: (
        "May problema ang app ngayon, pero totoo ang mga numerong ito at"
        " hindi sila nawawala. / The app is having trouble right now, but"
        " these numbers are real and they don't go away."
    ),
    SafeFloorReason.FACTS_CHANGED: (
        "May nagbago sa kwento mo, kaya kailangan kong i-update ang plano"
        " bago ito masundan. / Something you told me changed, so the plan"
        " needs updating before it can be followed. These offices are safe"
        " to contact meanwhile."
    ),
    SafeFloorReason.ACUTE_DISCLOSURE: (
        "Sinabi mo sa akin na nasa panganib ka ngayon. Nasa iyo pa rin ang"
        " desisyon — pero narito na ang mga numerong ito, at totoong tao"
        " ang sasagot. / You've told me you're in danger right now. The"
        " choice stays yours — but these numbers are here now, and real"
        " people answer them."
    ),
    SafeFloorReason.HELP_REQUESTED: (
        "You asked for help now. These offices are real, and real people"
        " answer them."
    ),
}

#: The stay-put line — suppressed under Imminent Danger (leaving may be
#: exactly what she needs to do).
HOLD_LINE = (
    "Huwag kang umalis sa amo mo bago ka makausap ang MWO — ang pagkakasunod"
    " ng hakbang mo ang magliligtas sa sahod mo. / Do not leave before"
    " speaking to the MWO — the order you act in protects your wage claim."
)

_TITLES: dict[Country, str] = {
    Country.SA: "Saudi Arabia — Mga totoong opisina na makakatulong / Real offices that can help",
    Country.QA: "Qatar — Mga totoong opisina na makakatulong / Real offices that can help",
    Country.KW: "Kuwait — Mga totoong opisina na makakatulong / Real offices that can help",
    Country.AE: "UAE — Mga totoong opisina na makakatulong / Real offices that can help",
    Country.UNKNOWN: "Mga totoong opisina na makakatulong / Real offices that can help",
}

#: Directory keys per country card, in render order. Resolved server-side
#: and dialability-filtered at build time — never number strings.
CARD_KEYS: dict[Country, tuple[str, ...]] = {
    Country.SA: (
        "mwo_riyadh",
        "mwo_alkhobar",
        "ph_embassy_riyadh_atn",
        "pcg_jeddah_atn",
        "dmw_orcc",
        "owwa_1348",
    ),
    Country.QA: (
        "mwo_doha",
        "mwo_doha_atn",
        "ph_embassy_doha_atn",
        "dmw_orcc",
        "owwa_1348",
    ),
    Country.KW: (
        "mwo_kuwait",
        "dfa_oumwa_atn",
        "dmw_orcc",
        "owwa_1348",
    ),
    Country.AE: (
        "mwo_dubai",
        "mwo_abu_dhabi",
        "ph_consulate_dubai_atn",
        "dmw_orcc",
        "owwa_1348",
    ),
    Country.UNKNOWN: (
        "dfa_oumwa_atn",
        "owwa_1348",
    ),
}


def build_card(
    country: Country,
    *,
    reason: SafeFloorReason,
    imminent_danger: bool,
) -> dict[str, Any]:
    """The fixed Safe Floor card for ``country``. Pure; no model, no store."""
    if country not in CARD_KEYS:
        country = Country.UNKNOWN
    return {
        "type": "safe_floor",
        "country": country.value,
        "title": _TITLES[country],
        "reason": reason.value,
        "reason_line": REASON_LINES[reason],
        "contacts": resolve_keys(list(CARD_KEYS[country]), country),
        "hold_line": None if imminent_danger else HOLD_LINE,
    }


#: Reasons that can be served straight from the zero-model cache: the
#: genuine service-down fallback, and a healthy press of the "I need help
#: now" button.
CACHED_REASONS: tuple[SafeFloorReason, ...] = (
    SafeFloorReason.SERVICE_DOWN,
    SafeFloorReason.HELP_REQUESTED,
)


def _build_cache() -> dict[tuple[Country, bool, SafeFloorReason], dict[str, Any]]:
    cache: dict[tuple[Country, bool, SafeFloorReason], dict[str, Any]] = {}
    for country in CARD_KEYS:
        for danger in (False, True):
            for reason in CACHED_REASONS:
                cache[(country, danger, reason)] = build_card(
                    country,
                    reason=reason,
                    imminent_danger=danger,
                )
    return cache


#: The zero-model hard fallback: precomputed at import, keyed by
#: (country, imminent_danger, reason). Rendering from here touches neither
#: the model nor the session store.
CACHED_CARDS: dict[tuple[Country, bool, SafeFloorReason], dict[str, Any]] = _build_cache()


def cached_card(
    country: Country = Country.UNKNOWN,
    *,
    imminent_danger: bool = False,
    reason: SafeFloorReason = SafeFloorReason.SERVICE_DOWN,
) -> dict[str, Any]:
    """The cached card for ``reason`` (SERVICE_DOWN by default); UNKNOWN
    when the country is unreadable. Never touches the model or the store."""
    return CACHED_CARDS.get(
        (country, imminent_danger, reason),
        CACHED_CARDS[(Country.UNKNOWN, imminent_danger, reason)],
    )
