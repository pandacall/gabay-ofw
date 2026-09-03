"""Per-country Safe Floor cards (issue #39, PRD #34).

One fixed, code-owned artifact per country. When no verified Plan can be
shown, she gets this — never an unverified sequence. Contacts are
resolved from the immutable directory and dialability-filtered; reason
lines are a fixed enum of hand-written, individually reviewed strings;
the "do not leave before speaking to the MWO" line is suppressed under
the Imminent Danger predicate.

Two render paths:

* **Hard fallback** — ``CACHED_CARDS`` is precomputed at import. When the
  session store or the extractor is down, the card renders from this
  cache with ZERO model calls.
* **Bounded outcome** — inside a working turn (no verified plan, HELD
  jurisdiction) DISPATCHER frames the card in its own words via the
  ``safe_floor_card`` tool; the card itself is fixed and streams to the
  UI as structured data outside the LLM text (ADR-0002's principle).

The Imminent Danger predicate proper is issue #41's scope; this module
ships the conservative, code-owned hook it will replace.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from app.directory import Country, resolve_keys

# ---------------------------------------------------------------------------
# Imminent Danger stub (issue #41 owns the real predicate).
# ---------------------------------------------------------------------------

#: Acuteness is a property of the enum member itself, a frozenset in code
#: — never a side table (PRD #34). Conservative stub: under possible
#: acute danger, suppressing the stay-put line is the safe direction.
#: CONFINED and PASSPORT_WITHHELD are chronic (the Gulf baseline).
ACUTE_SAFETY_FLAGS = frozenset({"PHYSICAL_ASSAULT_ONGOING", "THREAT_OF_HARM"})


def is_imminent_danger(case: Optional[dict[str, Any]]) -> bool:
    """Conservative code-owned hook — issue #41 replaces this with the
    full predicate (EMERGENCY button, mark_safe, long-gap re-ask)."""
    if not case:
        return False
    flags = case.get("safety_flags") or {}
    return any(flag in ACUTE_SAFETY_FLAGS for flag in flags)


# ---------------------------------------------------------------------------
# Reason lines: a fixed enum of hand-written strings.
# ---------------------------------------------------------------------------


class SafeFloorReason(str, Enum):
    NO_VERIFIED_PLAN = "NO_VERIFIED_PLAN"
    JURISDICTION_HELD = "JURISDICTION_HELD"
    SERVICE_DOWN = "SERVICE_DOWN"
    FACTS_CHANGED = "FACTS_CHANGED"


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


def _build_cache() -> dict[tuple[Country, bool], dict[str, Any]]:
    cache: dict[tuple[Country, bool], dict[str, Any]] = {}
    for country in CARD_KEYS:
        for danger in (False, True):
            cache[(country, danger)] = build_card(
                country,
                reason=SafeFloorReason.SERVICE_DOWN,
                imminent_danger=danger,
            )
    return cache


#: The zero-model hard fallback: precomputed at import, keyed by
#: (country, imminent_danger). Rendering from here touches neither the
#: model nor the session store.
CACHED_CARDS: dict[tuple[Country, bool], dict[str, Any]] = _build_cache()


def cached_card(
    country: Country = Country.UNKNOWN, *, imminent_danger: bool = False
) -> dict[str, Any]:
    """The cached SERVICE_DOWN card; UNKNOWN when the country is unreadable."""
    return CACHED_CARDS.get(
        (country, imminent_danger), CACHED_CARDS[(Country.UNKNOWN, imminent_danger)]
    )
