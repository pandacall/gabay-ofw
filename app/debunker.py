"""DEBUNKER: the claim-template classifier specialist (issue #47, PRD #34).

A single-turn LlmAgent attached via ``sub_agents=[...]`` on DISPATCHER —
google-adk 2.8.0 auto-wraps a ``mode='single_turn'`` sub-agent as a tool
named after the agent (no ``AgentTool``). It sees none of the
conversation: its input is the typed :class:`ClaimSet` plus session
state, its output the typed :class:`Verdicts` — per claim FALSE / TRUE /
NOT_COVERED.

``search_corpus`` is a DETERMINISTIC CLASSIFIER over the closed
claim-template corpus (``app.debunker_corpus``): normalization plus
hand-written stem groups, no embeddings. Everything that must be true —
the verdict, the cited rebuttal in her language, the register set by the
Source Tier, the MWO routing on NOT_COVERED, the Case write on a
plan-relevant FALSE — is computed by :func:`debunk_claims`, a pure
function, and returned as the tool result. The model's only job is to
relay it.

NOT_COVERED ROUTES rather than shrugs: "I can't verify that; the MWO
can, here's the number" — the same shape as the Safe Floor. The routing
rows come from the immutable directory (``app.directory``), channel-
tagged and dialability-filtered for her country, never generated; on the
way back they cross ROUTING_GUARD again, which re-filters by channel
(``search_corpus`` and the DEBUNKER tool itself are both on the guard's
allowlist and both rails apply).

A FALSE verdict on a plan-relevant belief writes to the Case via
``merge_case`` with ``source="debunker"`` provenance, so a later Plan
resting on that belief goes stale via the input-hash mechanism (the
staleness check itself is issue #43).
"""

from __future__ import annotations

import datetime
from typing import Literal, Optional

from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from google.adk.tools import ToolContext
from pydantic import BaseModel, Field

from app.case import merge_case
from app.debunker_corpus import CLAIM_TEMPLATES, ClaimTemplate
from app.directory import (
    Channel,
    Country,
    office_directory_rows,
    resolve_case_country,
)
from app.guard import guard_before_tool
from app.rules.schema import SourceTier
from app.state_keys import CASE, CASE_MUTATIONS

Language = Literal["en", "tl", "taglish", "ceb", "other"]

#: Languages rendered with the Tagalog rebuttal; everything else gets
#: English. Cebuano deliberately falls back to English rather than to a
#: language she did not write in.
_TAGALOG_LANGUAGES = frozenset({"tl", "taglish"})


class ClaimSet(BaseModel):
    """Typed input: the claims she reports being told, in her words."""

    claims: list[str] = Field(
        description=(
            "Each claim exactly as she reported being told it, one string "
            "per claim, in her own words."
        )
    )
    language: Language = Field(
        default="en",
        description="The language of her current message.",
    )


class VerdictItem(BaseModel):
    claim: str
    verdict: Literal["FALSE", "TRUE", "NOT_COVERED"]
    rebuttal: Optional[str] = None
    source_name: Optional[str] = None


class Verdicts(BaseModel):
    """Typed output: one verdict per claim, in input order."""

    verdicts: list[VerdictItem]


# ---------------------------------------------------------------------------
# Deterministic classification
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Lowercase, diacritics stripped, punctuation to spaces, collapsed."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    cleaned = "".join(ch if ch.isalnum() else " " for ch in stripped)
    return " ".join(cleaned.split())


def _stem_matches(stem: str, norm: str, tokens: list[str]) -> bool:
    """One stem against normalized text. Three deterministic rules:

    - a multi-word stem matches at a word boundary prefix (so
      "two year" matches "two years");
    - a short or numeric stem matches only as an exact token (so "noc"
      never matches inside another word);
    - any other stem matches as a substring of a token (so "bayar"
      matches the Tagalog-inflected "nababayaran").
    """
    if " " in stem:
        return f" {stem}" in f" {norm}"
    if len(stem) < 4 or stem.isdigit():
        return stem in tokens
    return any(stem in token for token in tokens)


def classify_claim(text: str) -> ClaimTemplate | None:
    """Deterministically classifies one claim against the closed corpus.

    A claim matches a template when every stem in any one of its stem
    groups matches. Template order in CLAIM_TEMPLATES is precedence: the
    first match wins. Unknown claims return None — NOT_COVERED — always.
    """
    norm = _normalize(text)
    tokens = norm.split()
    for template in CLAIM_TEMPLATES:
        for group in template.match_stems:
            if all(_stem_matches(stem, norm, tokens) for stem in group):
                return template
    return None


def _rebuttal_for(template: ClaimTemplate, language: str) -> str:
    if language in _TAGALOG_LANGUAGES:
        return template.rebuttal_tl
    return template.rebuttal_en


def mwo_routing(country: Country) -> dict:
    """The code-owned NOT_COVERED routing payload for ``country``.

    Same shape of promise as the Safe Floor: route to a real party. The
    rows come from the immutable directory, channel-tagged (so
    ROUTING_GUARD re-filters them on the way back) and dialability-
    filtered for her country — a number she cannot dial ships only as a
    Manila-relay row. Never a generated number.
    """
    return {
        "authority": "MWO (Migrant Workers Office)",
        "rows": office_directory_rows(country),
        "directory_note": (
            "MWO contact details are in the official DMW directory at "
            "dmw.gov.ph"
        ),
    }


def _routing_contact(rows: list[dict]) -> dict | None:
    """The single row the fixed message names: a dialable MWO row first,
    then any dialable row. None when nothing is dialable from here."""
    for row in rows:
        if (
            row.get("channel") == Channel.MWO.value
            and row.get("dial_mode") == "dialable"
        ):
            return row
    for row in rows:
        if row.get("dial_mode") == "dialable":
            return row
    return None


def _not_covered_message(language: str, routing: dict) -> str:
    """The fixed NOT_COVERED line. Any number is interpolated from the
    directory rows in the routing payload, so the text can never drift
    from the directory."""
    contact = _routing_contact(routing.get("rows") or [])
    if language in _TAGALOG_LANGUAGES:
        if contact is not None:
            return (
                "Hindi ko ito ma-verify — pero kaya ito i-verify ng MWO. "
                f"Tawagan ang {contact['label']} sa {contact['phone']}, o "
                "hanapin ang MWO mo sa opisyal na DMW directory sa "
                "dmw.gov.ph."
            )
        return (
            "Hindi ko ito ma-verify — pero kaya ito i-verify ng MWO. "
            "Hanapin ang MWO mo sa opisyal na DMW directory sa "
            "dmw.gov.ph; ang mga numero sa listahang kasama nito ay para "
            "sa kasama mo sa Pilipinas na tatawag para sa iyo."
        )
    if contact is not None:
        return (
            "I can't verify that — but the MWO can. Call the "
            f"{contact['label']} at {contact['phone']}, or find your MWO "
            "in the official DMW directory at dmw.gov.ph."
        )
    return (
        "I can't verify that — but the MWO can. Find your MWO in the "
        "official DMW directory at dmw.gov.ph; the numbers listed with "
        "this are for someone in the Philippines to call for you."
    )


def debunk_claims(
    claims: list[str],
    language: str = "en",
    country: Country = Country.UNKNOWN,
) -> tuple[dict, dict | None]:
    """Pure core: verdicts payload plus the CaseDelta (or None).

    Returns ``(payload, delta)`` where ``payload`` is the code-owned
    verdicts structure (one entry per claim, input order) and ``delta``
    is the CaseDelta to merge when any plan-relevant belief was
    verdicted FALSE.
    """
    verdicts: list[dict] = []
    delta_claims: dict[str, dict] = {}
    for text in claims:
        template = classify_claim(text)
        # A template scoped to specific jurisdictions is never asserted
        # outside them (or for UNKNOWN): the claim fails closed to
        # NOT_COVERED and routes — the NOC entry is false IN QATAR, not
        # everywhere.
        if (
            template is not None
            and template.applies_in is not None
            and country.value not in template.applies_in
        ):
            template = None
        if template is None:
            routing = mwo_routing(country)
            verdicts.append(
                {
                    "claim": text,
                    "verdict": "NOT_COVERED",
                    "template_id": None,
                    "message": _not_covered_message(language, routing),
                    "routing": routing,
                }
            )
            continue
        primary = template.citations[0]
        verdicts.append(
            {
                "claim": text,
                "verdict": template.verdict,
                "template_id": template.template_id,
                "rebuttal": _rebuttal_for(template, language),
                "tier": template.tier.value,
                "source_name": primary.source_name,
                "reference": primary.reference,
                "url": primary.url,
            }
        )
        if template.verdict == "FALSE" and template.plan_relevant:
            delta_claims[template.case_field] = {
                "value": "FALSE",
                "confidence": (
                    "high"
                    if template.tier is SourceTier.TIER_1
                    else "medium"
                ),
            }
    payload = {"verdicts": verdicts, "language": language}
    delta = {"claims": delta_claims} if delta_claims else None
    return payload, delta


# ---------------------------------------------------------------------------
# The tool and the agent
# ---------------------------------------------------------------------------


def search_corpus(
    claims: list[str],
    tool_context: ToolContext,
    language: str = "en",
) -> dict:
    """Classifies claims against the closed template corpus.

    Deterministic — no model, no embeddings. The user's country is
    resolved server-side from her Case (the model never supplies it), so
    NOT_COVERED routing rows are dialability-filtered for where she is.
    On a plan-relevant FALSE it merges the debunk into the Case with
    ``source="debunker"`` provenance (user-confirmed values are never
    reverted; ``merge_case`` records a disagreement as a Conflict
    instead).
    """
    case = tool_context.state.get(CASE)
    country = resolve_case_country(case if isinstance(case, dict) else None)
    payload, delta = debunk_claims(claims, language, country)
    if delta is not None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tool_context.state[CASE] = merge_case(
            case if isinstance(case, dict) else None,
            delta,
            source="debunker",
            now=now,
        )
        # Append, never assign (ADR-0008 amendment / a code-review
        # regression caught before it shipped): each tool call gets its
        # own ToolContext, and two search_corpus calls in one model
        # response must never have the second's mutation replace the
        # first's — read whatever this turn has already accumulated and
        # add to it.
        existing = list(tool_context.state.get(CASE_MUTATIONS) or [])
        tool_context.state[CASE_MUTATIONS] = existing + [
            {"op": "merge", "delta": delta, "source": "debunker", "now": now}
        ]
    return payload


_DEBUNKER_INSTRUCTION = """\
You are DEBUNKER. You receive claims a Filipino overseas worker reports
having been told, and you verdict each one.

Call search_corpus exactly once, passing every claim unchanged and the
given language. Build your verdicts strictly from its result:

- Copy each verdict (FALSE / TRUE / NOT_COVERED) exactly.
- For FALSE and TRUE, copy the returned rebuttal text verbatim as the
  rebuttal and the returned source_name as the source.
- For NOT_COVERED, copy the returned message verbatim as the rebuttal —
  it routes to the MWO. Never answer with a bare "I don't know".

Never invent, add, or alter a phone number, law, date, citation, or
verdict. Everything you output must come from the tool result.
"""


def build_debunker(llm: BaseLlm) -> LlmAgent:
    """Builds the DEBUNKER single-turn specialist.

    Attached via ``sub_agents=[...]`` on DISPATCHER; ADK 2.8.0 wraps it
    as a tool named DEBUNKER with the ClaimSet schema as parameters.
    Transfers are disallowed both ways: specialists never chat and never
    call one another (they couple only through the Case). Its tool calls
    cross ROUTING_GUARD on both rails: the App plugin, plus this agent's
    own before-tool callback (the same second rail DISPATCHER carries).
    """
    return LlmAgent(
        name="DEBUNKER",
        mode="single_turn",
        model=llm,
        description=(
            "Verdicts claims she reports being told (a claimed debt, "
            "rule, or restriction): FALSE / TRUE / NOT_COVERED per "
            "claim, with a cited rebuttal in her language. Pass every "
            "claim exactly as she reported it."
        ),
        instruction=_DEBUNKER_INSTRUCTION,
        input_schema=ClaimSet,
        output_schema=Verdicts,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        tools=[search_corpus],
        before_tool_callback=guard_before_tool,
    )
