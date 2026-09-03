"""The immutable office directory (issue #39, PRD #34).

Code-owned, fixed at import: channel-tagged contact rows that
``office_directory`` returns and ``action_card`` resolves keys against.
The model never supplies a phone number — tools hand out rows from this
table, ROUTING_GUARD filters them by channel on the way back, and
``action_card`` accepts directory *keys*, never number strings.

Dialability is data, not prose: every entry records which host countries
its number can actually be dialed from, with a source for the claim (see
docs/safe-floor-dialability.md). Philippine short codes (1348, 1553,
1343) do not dial from the Gulf; they render only as "for someone in
Manila to call". MWO / embassy numbers render in international format.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class Channel(str, Enum):
    """The routing channel a directory row belongs to.

    ROUTING_GUARD's allowlist is enforced against this enum on tool
    RESULTS — argument spelling cannot bypass it. ``LOCAL_POLICE`` exists
    only so the refusal is nameable: no directory entry carries it, and
    the guard drops it even if a row ever did (defense in depth). A
    Saudi assault victim routed to local police faces documented
    counter-filed theft and zina charges (HRW).
    """

    MWO = "MWO"
    EMBASSY_ATN = "EMBASSY_ATN"
    OWWA_1348 = "OWWA_1348"
    DMW_HOTLINE = "DMW_HOTLINE"
    LOCAL_POLICE = "LOCAL_POLICE"


class Country(str, Enum):
    """Where the user is. UNKNOWN is a first-class, most-restrictive value."""

    SA = "SA"
    QA = "QA"
    KW = "KW"
    AE = "AE"
    PH = "PH"
    UNKNOWN = "UNKNOWN"


#: Host countries the app serves (the Gulf corridor).
HOST_COUNTRIES = frozenset({Country.SA, Country.QA, Country.KW, Country.AE})

_COUNTRY_PATTERNS: tuple[tuple[Country, tuple[str, ...]], ...] = (
    (Country.SA, ("saudi", "ksa", "riyadh", "jeddah", "dammam", "khobar")),
    (Country.QA, ("qatar", "doha")),
    (Country.KW, ("kuwait",)),
    (Country.AE, ("uae", "u.a.e", "emirates", "dubai", "abu dhabi", "sharjah")),
)


def resolve_country(text: Optional[str]) -> Country:
    """Maps a free-text country claim to a Country; anything else is UNKNOWN.

    UNKNOWN is more restrictive than known-dangerous, never less — an
    unmappable spelling narrows what the app will do, it never widens it.
    """
    if not text:
        return Country.UNKNOWN
    lowered = text.lower()
    for country, needles in _COUNTRY_PATTERNS:
        if any(needle in lowered for needle in needles):
            return country
    return Country.UNKNOWN


def resolve_case_country(case: Optional[dict[str, Any]]) -> Country:
    """The user's country from her Case; UNKNOWN when absent.

    ``merge_case`` already guarantees a user-confirmed value is the
    claim's ``value`` (a later disagreeing extraction becomes a Conflict,
    never a revert), so reading ``value`` honors the PRD's
    "prefer user_confirmed" rule.
    """
    if not case:
        return Country.UNKNOWN
    claim = (case.get("claims") or {}).get("country")
    if not isinstance(claim, dict):
        return Country.UNKNOWN
    return resolve_country(claim.get("value"))


class DirectoryEntry(BaseModel):
    """One immutable directory row. Frozen: the table cannot drift at runtime."""

    model_config = ConfigDict(frozen=True)

    key: str
    channel: Channel
    #: Official, untranslated office name (PRD: never translated).
    label: str
    #: International format for anything dialable from abroad; a bare
    #: Philippine short code (e.g. 1348) only for PH-domestic relay rows.
    phone: str
    #: Which countries this number is verified dialable FROM.
    dialable_from: frozenset[Country]
    #: True for Philippine-side numbers that are meaningful for a family
    #: member in the Philippines to call on the user's behalf.
    ph_relay: bool = False
    #: The host country this office serves (None for PH-side entries).
    serves: Optional[Country] = None
    #: Dialability source (see docs/safe-floor-dialability.md).
    source_url: str
    source_note: str = ""

    def to_row(self, *, user_country: Country) -> Optional[dict[str, Any]]:
        """Renders this entry for a user in ``user_country``, or None.

        A number not dialable from her country ships only as a
        Manila-relay row ("for someone in Manila to call") — and only
        when the entry is a Philippine-side relay number. Anything else
        undialable is dropped, never rendered as if she could call it.
        """
        if user_country in self.dialable_from:
            dial_mode = "dialable"
        elif self.ph_relay:
            dial_mode = "manila_relay"
        else:
            return None
        return {
            "key": self.key,
            "channel": self.channel.value,
            "label": self.label,
            "phone": self.phone,
            "dial_mode": dial_mode,
            "note": (
                "Para sa kasama mo sa Pilipinas na tatawag para sa iyo / "
                "for someone in the Philippines to call for you"
                if dial_mode == "manila_relay"
                else self.source_note
            ),
        }


# The table itself. Every number's reachability is documented in
# docs/safe-floor-dialability.md before it ships; an unverifiable number
# does not go on a card (fail closed). Notable non-entries: MWO Jeddah
# (official site publishes no phone; the DMW directory PDF's number fails
# Saudi number-length validation) and DMW hotline "1553" (not found on
# any official source — the verified overseas DMW line is the ORCC).
_GULF = frozenset({Country.SA, Country.QA, Country.KW, Country.AE})
_ANYWHERE = _GULF | frozenset({Country.PH})

_DMW_MWO_DIRECTORY_PDF = (
    "https://dmw.gov.ph/archives/v1/resources/dsms/DMW/"
    "MWO-Directory-and-Jurisdiction-as-of-13-March-2026.pdf"
)

_ENTRIES: tuple[DirectoryEntry, ...] = (
    # ----- Saudi Arabia -----
    DirectoryEntry(
        key="mwo_riyadh",
        channel=Channel.MWO,
        label="MWO Riyadh (Migrant Workers Office)",
        phone="+966 50 285 0944",
        dialable_from=frozenset({Country.SA}),
        serves=Country.SA,
        source_url=_DMW_MWO_DIRECTORY_PDF,
        source_note="Saudi mobile; also on riyadhpe.dfa.gov.ph/contact-us",
    ),
    DirectoryEntry(
        key="mwo_alkhobar",
        channel=Channel.MWO,
        label="MWO Al Khobar / Eastern Region (Migrant Workers Office)",
        phone="+966 56 232 9926",
        dialable_from=frozenset({Country.SA}),
        serves=Country.SA,
        source_url=_DMW_MWO_DIRECTORY_PDF,
        source_note="Saudi mobile; DMW MWO Directory 13 Mar 2026",
    ),
    DirectoryEntry(
        key="ph_embassy_riyadh_atn",
        channel=Channel.EMBASSY_ATN,
        label="Philippine Embassy Riyadh — Assistance to Nationals (ATN)",
        phone="+966 56 989 3301",
        dialable_from=frozenset({Country.SA}),
        serves=Country.SA,
        source_url="https://riyadhpe.dfa.gov.ph/contact-us",
        source_note="Saudi mobile; 24/7 ATN hotline",
    ),
    DirectoryEntry(
        key="pcg_jeddah_atn",
        channel=Channel.EMBASSY_ATN,
        label="Philippine Consulate General Jeddah — ATN (western region)",
        phone="+966 55 521 9613",
        dialable_from=frozenset({Country.SA}),
        serves=Country.SA,
        source_url="https://jeddahpcg.dfa.gov.ph/113-help-for-filipinos",
        source_note="Saudi mobile; covers Makkah/Madinah/western KSA",
    ),
    # ----- Qatar -----
    DirectoryEntry(
        key="mwo_doha",
        channel=Channel.MWO,
        label="MWO Qatar (Migrant Workers Office, Doha)",
        phone="+974 3318 2459",
        dialable_from=frozenset({Country.QA}),
        serves=Country.QA,
        source_url=_DMW_MWO_DIRECTORY_PDF,
        source_note="Qatari mobile; ATN line +974 5118 4242 on dohape.dfa.gov.ph",
    ),
    DirectoryEntry(
        key="mwo_doha_atn",
        channel=Channel.MWO,
        label="MWO Qatar — Assistance to Nationals (ATN)",
        phone="+974 5118 4242",
        dialable_from=frozenset({Country.QA}),
        serves=Country.QA,
        source_url="https://dohape.dfa.gov.ph/contact-us",
        source_note="Qatari mobile",
    ),
    DirectoryEntry(
        key="ph_embassy_doha_atn",
        channel=Channel.EMBASSY_ATN,
        label="Philippine Embassy Doha — hotline for nationals in distress",
        phone="+974 6644 6303",
        dialable_from=frozenset({Country.QA}),
        serves=Country.QA,
        source_url="https://dohape.dfa.gov.ph/contact-us",
        source_note="Qatari mobile",
    ),
    # ----- Kuwait -----
    DirectoryEntry(
        key="mwo_kuwait",
        channel=Channel.MWO,
        label="MWO Kuwait (Migrant Workers Office)",
        phone="+965 9403 9063",
        dialable_from=frozenset({Country.KW}),
        serves=Country.KW,
        source_url=_DMW_MWO_DIRECTORY_PDF,
        source_note="Kuwaiti mobile; alternates +965 6040 3858, +965 6558 5355",
    ),
    # The PH Embassy Kuwait ATN hotline is published only as image
    # banners on kuwaitpe.dfa.gov.ph and could not be text-verified from
    # an official source — it does NOT ship (fail closed). The MWO rows
    # above are the embassy compound's verified numbers.
    # ----- UAE -----
    DirectoryEntry(
        key="mwo_dubai",
        channel=Channel.MWO,
        label="MWO Dubai (Migrant Workers Office)",
        phone="+971 50 652 6626",
        dialable_from=frozenset({Country.AE}),
        serves=Country.AE,
        source_url=_DMW_MWO_DIRECTORY_PDF,
        source_note="UAE mobile; covers Dubai and northern emirates",
    ),
    DirectoryEntry(
        key="mwo_abu_dhabi",
        channel=Channel.MWO,
        label="MWO Abu Dhabi (Migrant Workers Office)",
        phone="+971 56 270 9157",
        dialable_from=frozenset({Country.AE}),
        serves=Country.AE,
        source_url=_DMW_MWO_DIRECTORY_PDF,
        source_note="UAE mobile; also on abudhabipe.dfa.gov.ph/contact-us",
    ),
    DirectoryEntry(
        key="ph_consulate_dubai_atn",
        channel=Channel.EMBASSY_ATN,
        label="Philippine Consulate General Dubai — Assistance to Nationals (ATN)",
        phone="+971 56 501 5756",
        dialable_from=frozenset({Country.AE}),
        serves=Country.AE,
        source_url="https://dubaipcg.dfa.gov.ph/contact-us",
        source_note="UAE mobile",
    ),
    # ----- Philippine-side (dialable internationally or Manila relay) -----
    DirectoryEntry(
        key="dfa_oumwa_atn",
        channel=Channel.EMBASSY_ATN,
        label="DFA Manila — Office of Migration Affairs (OUMA/OUMWA), Assistance to Nationals",
        phone="+63 2 8834 4996",
        # A Metro Manila geographic landline: dialable in international
        # format from any Gulf network (international toll applies).
        dialable_from=_ANYWHERE,
        serves=None,
        source_url="https://www.foi.gov.ph/requests/going-home-assistance/",
        source_note="DFA trunkline; alt +63 2 8834 4594",
    ),
    DirectoryEntry(
        key="dmw_orcc",
        channel=Channel.DMW_HOTLINE,
        label="DMW One Repatriation Command Center (ORCC), Manila",
        phone="+63 2 8722 1144",
        dialable_from=_ANYWHERE,
        serves=None,
        source_url=(
            "https://dfa.gov.ph/dfa-news/dfa-releasesupdate/34474-dfa-oumwa-"
            "is-renamed-as-office-of-the-undersecretary-for-migration-affairs"
        ),
        source_note="Manila landline; alt +63 2 8722 1155",
    ),
    DirectoryEntry(
        key="owwa_1348",
        channel=Channel.OWWA_1348,
        label="OWWA / DMW Hotline 1348",
        phone="1348",
        # A Philippine-carrier short code: NOT dialable from any Gulf
        # network. Ships only as "for someone in Manila to call"; the
        # published +63 2 1348 overseas variant is not confirmed on
        # owwa.gov.ph, so it does not ship (fail closed).
        dialable_from=frozenset({Country.PH}),
        ph_relay=True,
        serves=None,
        source_url=(
            "https://dfa.gov.ph/dfa-news/dfa-releasesupdate/34474-dfa-oumwa-"
            "is-renamed-as-office-of-the-undersecretary-for-migration-affairs"
        ),
        source_note="PH-domestic short code (dial 1348 within the Philippines)",
    ),
)


def _by_key() -> dict[str, DirectoryEntry]:
    return {entry.key: entry for entry in _ENTRIES}


def office_directory_rows(user_country: Country) -> list[dict[str, Any]]:
    """Channel-tagged rows for a user in ``user_country``.

    Includes the offices serving her country plus Philippine-side relay
    rows. For UNKNOWN, only entries that serve no specific host country
    (DFA/OWWA/DMW Manila-side) are returned — the guard independently
    narrows the channels.
    """
    rows: list[dict[str, Any]] = []
    for entry in _ENTRIES:
        if entry.serves is not None and entry.serves is not user_country:
            continue
        row = entry.to_row(user_country=user_country)
        if row is not None:
            rows.append(row)
    return rows


def resolve_keys(keys: list[str], user_country: Country) -> list[dict[str, Any]]:
    """Server-side key -> entry resolution with dialability filtering.

    Unknown keys are dropped, never guessed; a key whose number is not
    dialable (and not a Manila relay) is dropped too.
    """
    table = _by_key()
    rows: list[dict[str, Any]] = []
    for key in keys:
        entry = table.get(key)
        if entry is None:
            continue
        row = entry.to_row(user_country=user_country)
        if row is not None:
            rows.append(row)
    return rows
