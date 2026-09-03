"""Typed boundary of RECOURSE_ROUTER (issue #48, PRD #34).

RECOURSE_ROUTER is a single-turn specialist: it sees NONE of the
conversation. Its entire input is :class:`RecourseRouteIn` — Case-derived
facts (country, tenure, grievances, agency) plus ``family_region``, an
*attribute* of the case, never its subject (PRD #48: "family as an
attribute, not the subject" — the worker herself stays the subject of
every route; her family's location only affects which PH-side office a
route names). Its entire output is a tuple of :class:`RecourseRoute`
objects — the design session's shape, verbatim::

    RecourseRoute{venue, prerequisites[], executor: SELF|KIN|EITHER,
                  what_to_bring[], source}

There is deliberately no free-text ``request`` parameter anywhere, the
same discipline as every other specialist's ``input_schema``
(COMPLAINT_DRAFTER, FILING_SEQUENCER, PROOF_BUILDER).

> **ADR reference note** (mirrors ``docs/rules-corpus.md``'s own note):
> issue #48 and PRD #34 cite ADR-0004 (topology) and ADR-0005 (source
> tiers). Those ADR files are not yet committed to ``docs/adr/`` (the repo
> currently holds ADR-0001..0003, 0006, 0007) — this module implements the
> topology and tier semantics exactly as specified verbatim in PRD #34;
> when ADR-0004/0005 land, this module should be checked against them.

Executor is one of :class:`Executor` — ``SELF`` (the worker acts, e.g.
filing SEnA herself from abroad through the MWO/POLO, DOLE's ARMS portal,
or an SPA representative — verified in the design session), ``KIN`` (only
a family member in the Philippines can realistically act, e.g. walking
into a PH office), or ``EITHER`` (both are real paths). ``family_region``
(:class:`FamilyRegion`) is optional and closed-enum: ``None`` means it was
never asked, and a PH-side venue is then named generically rather than
guessing Metro Manila (PRD #48: "never Manila-centric").
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.complaint.schema import AgencyInfo
from app.rules.schema import Citation, Grievance, Jurisdiction, TenureBucket


class Executor(str, Enum):
    """Who can realistically carry out a route's filing step.

    ``SELF`` only appears on a route this module can concretely source as
    executable by the worker herself while still abroad (PRD #48: SEnA is
    filable from abroad, so ``SELF`` is real for that route) — never
    asserted by default just because a route exists.
    """

    SELF = "self"
    KIN = "kin"
    EITHER = "either"


class FamilyRegion(str, Enum):
    """Where the worker's family is, in the Philippines.

    A closed binary, not a full regional breakdown: the sourced fork this
    corpus branches on (issue #48's regional-office fixture) is only
    Metro Manila versus everywhere else — DMW's own office network is
    NCR plus regional/satellite offices (see module docstring in
    :mod:`app.recourse.routes`). Deliberately optional on
    :class:`RecourseRouteIn`: ``None`` means DISPATCHER never asked, and a
    route is then named without assuming Metro Manila.
    """

    METRO_MANILA = "metro_manila"
    OUTSIDE_METRO_MANILA = "outside_metro_manila"


class RecourseRoute(BaseModel):
    """One open door: where to go, what must be true first, who can walk
    through it, what to bring, and the source it rests on.

    The design session's shape, verbatim — no field beyond these five.
    """

    model_config = ConfigDict(frozen=True)

    venue: str
    prerequisites: tuple[str, ...] = ()
    executor: Executor
    what_to_bring: tuple[str, ...] = ()
    source: Citation


class RecourseRouteIn(BaseModel):
    """RECOURSE_ROUTER's closed-enum input — no free-text field anywhere.

    Mirrors :class:`~app.sequencer.SequencerIn`'s shape (country, tenure,
    grievances) plus :class:`~app.complaint.schema.AgencyInfo` — reused
    from COMPLAINT_DRAFTER's typed boundary, never redefined — and the
    optional family attribute this specialist adds.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    country: Jurisdiction
    tenure: TenureBucket
    grievances: tuple[Grievance, ...]
    agency: AgencyInfo
    family_region: Optional[FamilyRegion] = None


class RecourseRouterOut(BaseModel):
    """RECOURSE_ROUTER's single-turn structured result: every open door,
    in the order the routes were built — never a refusal shape, since an
    unlicensed agency or an already-out worker is itself a valid route
    (illegal recruitment, OWWA repatriation), not a dead end."""

    model_config = ConfigDict(frozen=True)

    routes: tuple[RecourseRoute, ...]
