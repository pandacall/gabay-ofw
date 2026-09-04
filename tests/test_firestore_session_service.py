"""Emulator tests for the v6 Firestore session service contract.

Requires the Firestore emulator (FIRESTORE_EMULATOR_HOST). Covers the
issue #37 acceptance criteria: the persistence round-trip (a Case field
survives an instance recycle, ``temp:`` state never persists), scoped
state living off the session document, the concurrent-write retry that
never clobbers a safety flag, and a failed append surfacing an error
instead of silently dropping a state delta.

Also covers issue #70 (ADR-0008)'s safety fix: a Case/Plan write persists
the MUTATION, replayed inside the transaction against the freshly-read
stored Case — the EMERGENCY press surviving an in-flight turn's commit,
a Safety Flag surviving a concurrent writer, a user correction replayed
late still winning outright, and an unrecognised mutation leaving the
Case untouched rather than raising or clearing it.
"""

import asyncio
import json
import os
from uuid import uuid4

import pytest
from google.adk.errors import StaleSessionError
from google.adk.errors.session_not_found_error import SessionNotFoundError
from google.adk.events import Event, EventActions
from google.cloud import firestore

from app.firestore_session_service import FirestoreSessionService
from app.rules import Citation, Grievance, Jurisdiction, SourceTier, TenureBucket
from app.sequencer import ActionClass, PlanStep, SequencerIn
from app.state_keys import CASE, CASE_MUTATIONS, PLAN, PLAN_ACTIVE, PLAN_MUTATIONS

pytestmark = pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"),
    reason="requires the Firestore emulator",
)

APP_NAME = "gabay-ofw"


def _db():
    return firestore.Client(project="gabay-ofw-rules-test")


def _event(state_delta: dict) -> Event:
    return Event(
        author="DISPATCHER",
        invocation_id=f"inv-{uuid4().hex}",
        actions=EventActions(state_delta=state_delta),
    )


def test_round_trip_survives_recycle_and_never_persists_temp_state():
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"round-trip-{uuid4().hex}"

    async def scenario() -> str:
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        await service.append_event(
            session,
            _event(
                {
                    "case_country": "SA",
                    "temp:extraction_scratch": "raw narrative text",
                    "user:preferred_language": "tl",
                }
            ),
        )
        # The temp value is visible in memory for the rest of the invocation.
        assert session.state["temp:extraction_scratch"] == "raw narrative text"
        session_id = session.id
        del session  # simulate the instance recycle

        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session_id
        )
        assert resumed is not None
        assert resumed.state["case_country"] == "SA"
        assert "temp:extraction_scratch" not in resumed.state
        assert resumed.state["user:preferred_language"] == "tl"
        assert len(resumed.events) == 1
        return session_id

    session_id = asyncio.run(scenario())

    session_doc = (
        db.collection("users")
        .document(uid)
        .collection("sessions")
        .document(session_id)
        .get()
        .to_dict()
    )
    # Scoped keys live off the session document; temp: was never written.
    assert session_doc["state"] == {"case_country": "SA"}
    assert session_doc["revision"] == 1
    user_state = (
        db.collection("users")
        .document(uid)
        .collection("adkUserState")
        .document(APP_NAME)
        .get()
        .to_dict()
    )
    assert user_state == {"preferred_language": "tl"}
    # The old Contract Check collection path is never written.
    old_path = db.collection("users").document(uid).collection("contractChecks")
    assert list(old_path.stream()) == []


def test_stale_append_retries_once_and_preserves_concurrent_safety_flag():
    service = FirestoreSessionService(_db())
    uid = f"stale-retry-{uuid4().hex}"

    async def scenario():
        created = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer_a = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        writer_b = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        # A concurrent turn writes a safety flag first.
        await service.append_event(
            writer_a, _event({"safety_flag": "PHYSICAL_ASSAULT_ONGOING"})
        )
        # writer_b is now stale; the retry path must re-apply its delta on
        # top of the flag, never overwrite it.
        await service.append_event(writer_b, _event({"case_country": "SA"}))

        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        assert resumed.state["safety_flag"] == "PHYSICAL_ASSAULT_ONGOING"
        assert resumed.state["case_country"] == "SA"
        assert len(resumed.events) == 2
        # The retried writer's in-memory session picked up the flag too.
        assert writer_b.state["safety_flag"] == "PHYSICAL_ASSAULT_ONGOING"

    asyncio.run(scenario())


def test_append_surfaces_stale_error_when_retry_also_loses(monkeypatch):
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"stale-exhausted-{uuid4().hex}"

    async def scenario():
        created = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        rival = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        await service.append_event(
            rival, _event({"safety_flag": "PHYSICAL_ASSAULT_ONGOING"})
        )

        # Another turn keeps landing between the retry's re-read and its
        # transaction, so the single retry also loses the race.
        original_read = service._read_revision

        def racing_read(session_ref):
            revision = original_read(session_ref)
            session_ref.update({"revision": firestore.Increment(1)})
            return revision

        monkeypatch.setattr(service, "_read_revision", racing_read)

        with pytest.raises(StaleSessionError):
            await service.append_event(writer, _event({"case_country": "SA"}))

        monkeypatch.setattr(service, "_read_revision", original_read)
        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=created.id
        )
        # The failed append surfaced the error without half-applying its
        # delta or clobbering the concurrent write.
        assert "case_country" not in resumed.state
        assert resumed.state["safety_flag"] == "PHYSICAL_ASSAULT_ONGOING"
        assert len(resumed.events) == 1

    asyncio.run(scenario())


def test_append_to_deleted_session_surfaces_error():
    service = FirestoreSessionService(_db())
    uid = f"deleted-append-{uuid4().hex}"

    async def scenario():
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        await service.delete_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        with pytest.raises(SessionNotFoundError):
            await service.append_event(session, _event({"case_country": "SA"}))

    asyncio.run(scenario())


def test_partial_event_is_not_persisted():
    service = FirestoreSessionService(_db())
    uid = f"partial-{uuid4().hex}"

    async def scenario():
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        event = _event({"case_country": "SA"})
        event.partial = True
        await service.append_event(session, event)
        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        assert resumed.events == []
        assert "case_country" not in resumed.state

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Case mutation replay (issue #70, ADR-0008): the safety fix at the heart
# of this slice, exercised against a REAL Firestore transaction.
# ---------------------------------------------------------------------------


def _case_mutation_event(
    *, pre_merged_blob: dict | None, mutations: list[dict]
) -> Event:
    """An Event carrying BOTH a same-turn pre-merged Case blob (the
    convenience write every writer also makes for immediate in-turn
    reads) and the recorded mutations — proving the mutation wins."""
    delta: dict = {CASE_MUTATIONS: mutations}
    if pre_merged_blob is not None:
        delta[CASE] = pre_merged_blob
    return _event(delta)


def test_emergency_press_survives_a_turn_already_in_flight():
    """The concrete failure ADR-0008 exists to close: a DISPATCHER turn
    is already in flight (holding a stale in-memory Case) when she taps
    EMERGENCY. The turn's eventual commit — a pre-merged blob computed
    BEFORE the tap, plus its own recorded mutation — must never erase
    the press, because the transaction re-runs the merge against the
    freshly-stored (already-pressed) Case rather than trusting the blob.
    """
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"emergency-in-flight-{uuid4().hex}"

    async def scenario():
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        in_flight_writer = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        # She taps EMERGENCY: a session-less write straight to her
        # user-scoped Case, exactly like ChatService.press_emergency_button.
        pressed_at = "2026-09-04T00:00:00+00:00"
        await service.append_user_mutation(
            app_name=APP_NAME,
            user_id=uid,
            case_mutations=[{"op": "press_emergency_button", "now": pressed_at}],
        )

        # The in-flight DISPATCHER turn now commits — its own pre-merged
        # blob was computed BEFORE the tap (no emergency), but it also
        # carries its own recorded mutation.
        stale_blob = {
            "claims": {"country": {"value": "Saudi Arabia", "source": "extraction"}},
            "safety_flags": {},
            "language": None,
            "emergency": {
                "active": False,
                "button_pressed_at": None,
                "marked_safe_at": None,
                "flag_triggered_at": None,
                "last_turn_at": None,
                "resume_check_at": None,
            },
        }
        await service.append_event(
            in_flight_writer,
            _case_mutation_event(
                pre_merged_blob=stale_blob,
                mutations=[
                    {
                        "op": "merge",
                        "delta": {
                            "claims": {
                                "country": {
                                    "value": "Saudi Arabia",
                                    "confidence": "high",
                                }
                            }
                        },
                        "source": "extraction",
                        "now": "2026-09-03T23:59:59+00:00",
                    }
                ],
            ),
        )

        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        case = user_state["case"]
        assert case["emergency"]["active"] is True
        assert case["emergency"]["button_pressed_at"] == pressed_at
        assert case["claims"]["country"]["value"] == "Saudi Arabia"
        # The in-flight writer's own in-memory/event view is reconciled
        # to the true persisted Case too, not left showing the stale blob.
        assert in_flight_writer.state[CASE]["emergency"]["active"] is True

    asyncio.run(scenario())


def test_safety_flag_survives_a_concurrent_writers_later_commit():
    """A Safety Flag one writer merged must survive a SECOND writer's
    later commit, even though the second writer's own delta carries no
    flags at all (add-only, never cleared)."""
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"flag-survives-{uuid4().hex}"

    async def scenario():
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer_a = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        writer_b = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )

        await service.append_event(
            writer_a,
            _case_mutation_event(
                pre_merged_blob=None,
                mutations=[
                    {
                        "op": "merge",
                        "delta": {"safety_flags": ["PASSPORT_WITHHELD"]},
                        "source": "extraction",
                        "now": "2026-09-04T00:00:00+00:00",
                    }
                ],
            ),
        )
        # writer_b is now stale in the session-revision sense too; its
        # own mutation carries no flags, and its Case merge is unrelated.
        await service.append_event(
            writer_b,
            _case_mutation_event(
                pre_merged_blob=None,
                mutations=[
                    {
                        "op": "merge",
                        "delta": {
                            "claims": {
                                "employer_name": {
                                    "value": "Al Rashid",
                                    "confidence": "high",
                                }
                            }
                        },
                        "source": "extraction",
                        "now": "2026-09-04T00:05:00+00:00",
                    }
                ],
            ),
        )

        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        case = user_state["case"]
        assert "PASSPORT_WITHHELD" in case["safety_flags"]
        assert case["claims"]["employer_name"]["value"] == "Al Rashid"

    asyncio.run(scenario())


def test_user_correction_replayed_late_still_wins_and_resolves_conflict():
    """A one-tap ``user``-sourced correction, replayed AFTER a
    disagreeing extraction/document conflict was already stored, still
    wins outright and clears the Conflict — replay order never matters
    for who wins, only the source does."""
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"user-correction-late-{uuid4().hex}"

    async def scenario():
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer_a = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        writer_b = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )

        await service.append_event(
            writer_a,
            _case_mutation_event(
                pre_merged_blob=None,
                mutations=[
                    {
                        "op": "merge",
                        "delta": {
                            "claims": {
                                "country": {"value": "Saudi Arabia", "confidence": "high"}
                            }
                        },
                        "source": "extraction",
                        "now": "2026-09-04T00:00:00+00:00",
                    }
                ],
            ),
        )
        await service.append_event(
            writer_b,
            _case_mutation_event(
                pre_merged_blob=None,
                mutations=[
                    {
                        "op": "merge",
                        "delta": {
                            "claims": {"country": {"value": "Kuwait", "confidence": "high"}}
                        },
                        "source": "document",
                        "now": "2026-09-04T00:05:00+00:00",
                    }
                ],
            ),
        )

        resumed = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        assert resumed.state[CASE]["claims"]["country"]["conflicts"]

        writer_c = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        await service.append_event(
            writer_c,
            _case_mutation_event(
                pre_merged_blob=None,
                mutations=[
                    {
                        "op": "merge",
                        "delta": {
                            "claims": {"country": {"value": "Qatar", "confidence": "high"}}
                        },
                        "source": "user",
                        "now": "2026-09-04T00:10:00+00:00",
                    }
                ],
            ),
        )

        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        claim = user_state["case"]["claims"]["country"]
        assert claim["value"] == "Qatar"
        assert claim["user_confirmed"] is True
        assert claim["conflicts"] == []

    asyncio.run(scenario())


def test_unrecognised_mutation_leaves_the_stored_case_untouched():
    """An unrecognised ``"op"`` must never raise and must never clear the
    stored Case — it is simply skipped, leaving everything else this
    same event carries to apply normally."""
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"unknown-mutation-{uuid4().hex}"

    async def scenario():
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer_a = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        await service.append_event(
            writer_a,
            _case_mutation_event(
                pre_merged_blob=None,
                mutations=[
                    {
                        "op": "merge",
                        "delta": {"safety_flags": ["CONFINED"]},
                        "source": "extraction",
                        "now": "2026-09-04T00:00:00+00:00",
                    }
                ],
            ),
        )

        writer_b = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        await service.append_event(
            writer_b,
            _case_mutation_event(
                pre_merged_blob=None,
                mutations=[
                    {"op": "delete_everything", "now": "2026-09-04T00:05:00+00:00"}
                ],
            ),
        )

        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        case = user_state["case"]
        assert "CONFINED" in case["safety_flags"]

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Plan mutation replay (ADR-0008 amendment): the Plan gets the same
# commit-time-against-freshly-stored-state treatment as the Case, exercised
# against a REAL Firestore transaction via append_event.
# ---------------------------------------------------------------------------


def _plan_mutation_event(mutations: list[dict]) -> Event:
    return _event({PLAN_MUTATIONS: mutations})


def _citation() -> Citation:
    return Citation(
        source_name="Test Source",
        reference="Art. 1",
        url="https://example.org/law",
        tier=SourceTier.TIER_1,
    )


def _plan_step(step_id: str) -> PlanStep:
    return PlanStep(
        id=step_id,
        rule_citation=_citation(),
        grievance=Grievance.UNPAID_WAGES,
        file_where="SEnA",
        action_class=ActionClass.PROTECTIVE_REVERSIBLE,
        tier=SourceTier.TIER_1,
    )


def _seq_in(country: Jurisdiction = Jurisdiction.SA) -> SequencerIn:
    return SequencerIn(
        country=country,
        tenure=TenureBucket.EMPLOYED_IN_COUNTRY,
        grievances=(Grievance.UNPAID_WAGES,),
    )


def test_plan_publish_mutation_replayed_against_a_fresher_stored_plan():
    """A ``publish`` mutation recorded against the turn-start Plan must
    be replayed against whatever is ACTUALLY stored at commit time — a
    concurrent Conversation's DONE mark on the same Plan must survive a
    regeneration, not be silently discarded by a stale in-memory copy."""
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"plan-publish-fresh-{uuid4().hex}"

    async def scenario():
        seq_in = _seq_in()
        await service.append_user_mutation(
            app_name=APP_NAME,
            user_id=uid,
            plan_mutations=[
                {
                    "op": "publish",
                    "seq_in": seq_in.model_dump(mode="json"),
                    "steps": [_plan_step("row-1").model_dump(mode="json")],
                    "plan_id": "plan-1",
                    "now": "2026-09-04T00:00:00+00:00",
                }
            ],
        )

        # A concurrent writer marks the step DONE.
        await service.append_user_mutation(
            app_name=APP_NAME,
            user_id=uid,
            plan_mutations=[
                {
                    "op": "mark_step_done",
                    "plan_id": "plan-1",
                    "step_id": "row-1",
                    "now": "2026-09-04T00:01:00+00:00",
                }
            ],
        )

        # A regeneration mutation, computed against the version-1 Plan
        # BEFORE the DONE mark landed, commits through a Session/event.
        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        await service.append_event(
            writer,
            _plan_mutation_event(
                [
                    {
                        "op": "publish",
                        "seq_in": seq_in.model_dump(mode="json"),
                        "steps": [_plan_step("row-1").model_dump(mode="json")],
                        "plan_id": "plan-1",
                        "now": "2026-09-04T00:02:00+00:00",
                    }
                ]
            ),
        )

        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        stored_plan = user_state["plan"]
        assert stored_plan["steps"][0]["status"] == "DONE"
        assert stored_plan["version"] == 2

    asyncio.run(scenario())


def test_plan_mark_step_done_mismatch_is_a_noop_via_append_event():
    """A ``mark_step_done`` mutation whose ``plan_id`` no longer matches
    the freshly-stored Plan (a concurrent regeneration since it was
    recorded) must leave the stored Plan untouched, not mislabel a step
    on the wrong Plan."""
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"plan-mark-mismatch-{uuid4().hex}"

    async def scenario():
        seq_in = _seq_in()
        await service.append_user_mutation(
            app_name=APP_NAME,
            user_id=uid,
            plan_mutations=[
                {
                    "op": "publish",
                    "seq_in": seq_in.model_dump(mode="json"),
                    "steps": [_plan_step("row-1").model_dump(mode="json")],
                    "plan_id": "plan-1",
                    "now": "2026-09-04T00:00:00+00:00",
                }
            ],
        )

        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        await service.append_event(
            writer,
            _plan_mutation_event(
                [
                    {
                        "op": "mark_step_done",
                        "plan_id": "stale-plan-id",
                        "step_id": "row-1",
                        "now": "2026-09-04T00:01:00+00:00",
                    }
                ]
            ),
        )

        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        assert user_state["plan"]["steps"][0]["status"] == "PENDING"

    asyncio.run(scenario())


def test_plan_recheck_staleness_evaluated_against_freshly_stored_plan():
    """Two Conversations race a staleness recheck: A publishes a fresh,
    matching Plan; B's recheck was computed against an OLDER copy at
    B's turn start. Replayed against the FRESH stored Plan (A's), the
    recheck must find it not stale — closing the ADR-0008 amendment's
    race (a second Conversation's stale recheck must never overwrite a
    Plan another Conversation just verified)."""
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"plan-recheck-race-{uuid4().hex}"

    async def scenario():
        seq_in = _seq_in()
        await service.append_user_mutation(
            app_name=APP_NAME,
            user_id=uid,
            plan_mutations=[
                {
                    "op": "publish",
                    "seq_in": seq_in.model_dump(mode="json"),
                    "steps": [_plan_step("row-1").model_dump(mode="json")],
                    "plan_id": "plan-1",
                    "now": "2026-09-04T00:00:00+00:00",
                }
            ],
        )

        session = await service.create_session(app_name=APP_NAME, user_id=uid)
        writer = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=session.id
        )
        # B's recheck carries only the country it resolved this turn —
        # never a seq_in snapshot — so replay always compares against
        # the freshly-stored plan_seq_in, matching A's fresh Plan.
        await service.append_event(
            writer,
            _plan_mutation_event(
                [
                    {
                        "op": "recheck_staleness",
                        "country": "SA",
                        "now": "2026-09-04T00:05:00+00:00",
                    }
                ]
            ),
        )

        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        assert user_state["plan_active"] is True

    asyncio.run(scenario())


def test_get_user_state_and_append_user_mutation_need_no_session():
    """ADR-0008: the Case is user-scoped and belongs to her, not to any
    one Conversation — ``append_user_mutation``/``get_user_state`` never
    read, create, or touch a Session at all."""
    db = _db()
    service = FirestoreSessionService(db)
    uid = f"session-less-{uuid4().hex}"

    async def scenario():
        empty = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        assert empty == {}

        stored_user = await service.append_user_mutation(
            app_name=APP_NAME,
            user_id=uid,
            case_mutations=[
                {"op": "press_emergency_button", "now": "2026-09-04T00:00:00+00:00"}
            ],
        )
        assert stored_user["case"]["emergency"]["active"] is True

        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        assert user_state["case"]["emergency"]["active"] is True

        # No session was ever created for this uid.
        sessions = await service.list_sessions(app_name=APP_NAME, user_id=uid)
        assert sessions.sessions == []

    asyncio.run(scenario())


def test_emergency_button_resolves_country_from_stored_case_not_a_stateless_listing():
    """Regression pin (issue #79). ``FirestoreSessionService.list_sessions``
    carries only the denormalised Conversation-label keys (issue #73) —
    never the per-user Case/Plan, never other session state, never the
    events. So a caller that needs her Case still cannot get it from a
    listing and must read ``adkUserState`` (via ``get_user_state``).
    Exercised against the REAL backend: the EMERGENCY button must resolve
    her recorded country from
    ``adkUserState`` (via ``get_user_state``), so the cached card it
    renders unconditionally is for the RIGHT country rather than always
    UNKNOWN. A test that only ran against the in-memory fake could never
    catch this — it is the exact blind spot #79 tracked.
    """
    from google.adk.models import BaseLlm

    from app.chat import ChatService

    class _NeverCalledLlm(BaseLlm):
        model: str = "structural-test-only"

        async def generate_content_async(self, llm_request, stream: bool = False):
            raise AssertionError("the EMERGENCY button must never call the model")
            yield  # pragma: no cover - unreachable, satisfies the generator shape

    service = FirestoreSessionService(_db())
    chat_service = ChatService(session_service=service, llm=_NeverCalledLlm())
    uid = f"button-country-{uuid4().hex}"

    async def scenario():
        # She told Gabay her country in an earlier turn — a real Case
        # write, exactly like an ordinary DISPATCHER turn's extraction.
        await service.append_user_mutation(
            app_name=APP_NAME,
            user_id=uid,
            case_mutations=[
                {
                    "op": "merge",
                    "delta": {
                        "claims": {
                            "country": {"value": "Qatar", "confidence": "high"}
                        }
                    },
                    "source": "extraction",
                    "now": "2026-09-04T00:00:00+00:00",
                }
            ],
        )

        lines = [line async for line in chat_service.press_emergency_button(uid=uid)]
        cards = [json.loads(line) for line in lines if json.loads(line)["type"] == "card"]
        assert cards, "the button must render a card unconditionally"
        assert cards[0]["card"]["country"] == "QA"

    asyncio.run(scenario())


def test_conversations_list_and_delete_leave_the_shared_case_and_siblings_intact():
    """Issue #72 (ADR-0008): Conversations are threads over one
    user-scoped Case. Deleting one removes only its own document tree —
    the other Conversations and the ``adkUserState`` Case survive, so a
    frightened person's disclosures are never lost with a thread."""
    service = FirestoreSessionService(_db())
    uid = f"conversations-{uuid4().hex}"

    async def scenario():
        first = await service.create_session(app_name=APP_NAME, user_id=uid)
        second = await service.create_session(app_name=APP_NAME, user_id=uid)
        third = await service.create_session(app_name=APP_NAME, user_id=uid)

        # A fact disclosed in the first Conversation lands on the shared
        # user-scoped Case (a ``user:``-prefixed state delta).
        await service.append_event(
            first,
            _event(
                {
                    CASE: {"claims": {"country": {"value": "SA"}}},
                    CASE_MUTATIONS: [
                        {
                            "op": "merge",
                            "delta": {
                                "claims": {
                                    "country": {"value": "SA", "confidence": "high"}
                                }
                            },
                            "source": "extraction",
                            "now": "2026-09-04T00:00:00+00:00",
                        }
                    ],
                }
            ),
        )

        listed = await service.list_sessions(app_name=APP_NAME, user_id=uid)
        assert {s.id for s in listed.sessions} == {first.id, second.id, third.id}

        await service.delete_session(
            app_name=APP_NAME, user_id=uid, session_id=second.id
        )

        remaining = await service.list_sessions(app_name=APP_NAME, user_id=uid)
        assert {s.id for s in remaining.sessions} == {first.id, third.id}
        assert (
            await service.get_session(
                app_name=APP_NAME, user_id=uid, session_id=second.id
            )
            is None
        )

        # A Plan published from the first Conversation is the ONE live
        # Plan (ADR-0008): asking for filing steps in another Conversation
        # must surface this one, never build a rival. It is user-scoped
        # state, so a sibling Conversation reads exactly it.
        await service.append_event(
            first,
            _event({PLAN: {"steps": [{"id": "s1"}]}, PLAN_ACTIVE: True}),
        )

        # The shared Case is untouched by the Conversation delete, and is
        # still visible from a sibling Conversation — one Case, many
        # threads.
        user_state = await service.get_user_state(app_name=APP_NAME, user_id=uid)
        assert user_state["case"]["claims"]["country"]["value"] == "SA"
        assert user_state["plan"]["steps"] == [{"id": "s1"}]
        sibling = await service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=third.id
        )
        assert sibling.state.get(CASE)["claims"]["country"]["value"] == "SA"
        assert sibling.state.get(PLAN)["steps"] == [{"id": "s1"}]

    asyncio.run(scenario())


def test_list_sessions_carries_the_denormalised_conversation_label():
    """Issue #73 (ADR-0008): the Conversation label is stored in the
    session document's own state and surfaced by ``list_sessions`` — no
    per-Conversation state is loaded to build the rail, and the label
    rides on the doc that listing already reads."""
    from app.labels import CONVERSATION_LABEL, CONVERSATION_LABEL_SOURCE

    service = FirestoreSessionService(_db())
    uid = f"label-{uuid4().hex}"

    async def scenario():
        labelled = await service.create_session(app_name=APP_NAME, user_id=uid)
        plain = await service.create_session(app_name=APP_NAME, user_id=uid)
        await service.append_event(
            labelled,
            _event(
                {
                    CONVERSATION_LABEL: "passport",
                    CONVERSATION_LABEL_SOURCE: "derived",
                }
            ),
        )

        listed = {
            s.id: s
            for s in (
                await service.list_sessions(app_name=APP_NAME, user_id=uid)
            ).sessions
        }
        assert listed[labelled.id].state.get(CONVERSATION_LABEL) == "passport"
        assert listed[labelled.id].state.get(CONVERSATION_LABEL_SOURCE) == "derived"
        assert listed[plain.id].state.get(CONVERSATION_LABEL) is None
        # The per-user Case is still NOT loaded by a listing.
        assert CASE not in listed[labelled.id].state

    asyncio.run(scenario())
