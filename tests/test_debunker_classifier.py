"""DEBUNKER classifier pure suite (CI gate: deterministic, no model).

Known claims classify to their template; unknown claims yield
NOT_COVERED — deterministically. The most important assertions are what
must NOT happen: an unknown claim never matches, and a NOT_COVERED never
ships without the MWO routing resolved from the directory.
"""

import pytest

from app.debunker import classify_claim, debunk_claims, mwo_routing
from app.directory import Channel, Country, office_directory_rows

KNOWN_CLAIMS = [
    # placement_fee_debt — English, Tagalog, Taglish
    ("I still owe the agency my placement fee", "placement_fee_debt"),
    ("may utang pa ako sa placement fee", "placement_fee_debt"),
    (
        "Sabi ng agency, kinakaltas daw sa sweldo ko ang placement fee",
        "placement_fee_debt",
    ),
    ("They said I have a placement fee balance to pay", "placement_fee_debt"),
    # cannot_leave_until_repaid
    (
        "They told me I can't leave until I repay everything",
        "cannot_leave_until_repaid",
    ),
    (
        "Sabi nila hindi ako pwedeng umuwi hangga't hindi ko "
        "nababayaran ang utang ko",
        "cannot_leave_until_repaid",
    ),
    (
        "Hindi raw ako makakaalis dahil may utang pa ako",
        "cannot_leave_until_repaid",
    ),
    # passport_withholding_legal
    (
        "My employer says it's legal for him to keep my passport",
        "passport_withholding_legal",
    ),
    (
        "Sabi ng amo ko, karapatan daw niyang hawakan ang pasaporte ko",
        "passport_withholding_legal",
    ),
    (
        "Sabi nila legal daw na hawakan ng employer ang passport ko",
        "passport_withholding_legal",
    ),
    # noc_required_qatar
    ("They said I need an NOC before I can change jobs", "noc_required_qatar"),
    ("Kailangan ko raw ng NOC para makalipat ng amo", "noc_required_qatar"),
    (
        "He says I need a no objection certificate from him",
        "noc_required_qatar",
    ),
    # two_year_lock_in
    ("You must complete two years before you can go", "two_year_lock_in"),
    (
        "Sabi nila kailangan ko munang tapusin ang dalawang taon",
        "two_year_lock_in",
    ),
    ("I have to finish my contract first, they said", "two_year_lock_in"),
    # sa_ninety_day_withdrawal (TRUE verdict)
    (
        "Someone said if I withdraw my complaint I can't refile for 90 days",
        "sa_ninety_day_withdrawal",
    ),
    (
        "Totoo ba na 90 araw bago ko ulit maisampa ang reklamo ko?",
        "sa_ninety_day_withdrawal",
    ),
]

UNKNOWN_CLAIMS = [
    "Sabi nila makukulong daw ako kapag tumakas ako",
    "They said the embassy will deport me if I complain",
    "Kapag nag-file daw ako, hindi na ako makakabalik sa Pilipinas",
    "My salary will double next year, they promised",
    "",
]


class TestKnownClaimsClassify:
    @pytest.mark.parametrize(("claim", "expected"), KNOWN_CLAIMS)
    def test_known_claim_hits_its_template(self, claim, expected):
        template = classify_claim(claim)
        assert template is not None, f"expected {expected}, got NOT_COVERED"
        assert template.template_id == expected

    def test_classification_is_deterministic(self):
        for claim, _ in KNOWN_CLAIMS:
            first = classify_claim(claim)
            for _ in range(10):
                assert classify_claim(claim) is first

    def test_precedence_the_movement_restriction_wins_over_the_debt(self):
        # A combined claim carries both beliefs; the corpus order makes
        # the more dangerous one — "you can't leave" — win.
        combined = (
            "hindi ako pwedeng umuwi hangga't may utang ako sa placement fee"
        )
        assert classify_claim(combined).template_id == (
            "cannot_leave_until_repaid"
        )


class TestUnknownClaimsRefuse:
    @pytest.mark.parametrize("claim", UNKNOWN_CLAIMS)
    def test_unknown_claim_is_not_covered(self, claim):
        assert classify_claim(claim) is None

    def test_noc_never_matches_inside_another_word(self):
        # Short stems match exact tokens only.
        assert classify_claim("the innocuous notice was nocturnal") is None


class TestDebunkClaimsPayload:
    def test_false_verdict_carries_the_cited_rebuttal_in_her_language(self):
        payload, delta = debunk_claims(
            ["may utang pa ako sa placement fee"], language="taglish"
        )
        [entry] = payload["verdicts"]
        assert entry["verdict"] == "FALSE"
        assert entry["template_id"] == "placement_fee_debt"
        assert "Wala kang utang na placement fee" in entry["rebuttal"]
        assert entry["source_name"].startswith("2016 Revised POEA Rules")
        assert entry["tier"] == "tier_1"
        assert delta == {
            "claims": {
                "debunked_placement_fee_debt": {
                    "value": "FALSE",
                    "confidence": "high",
                }
            }
        }

    def test_english_claim_gets_the_english_rebuttal(self):
        payload, _ = debunk_claims(
            ["I still owe the agency my placement fee"], language="en"
        )
        assert "You owe no placement fee" in payload["verdicts"][0]["rebuttal"]

    def test_not_covered_routes_to_the_mwo_with_directory_rows(self):
        payload, delta = debunk_claims(
            ["sabi nila makukulong daw ako kapag tumakas ako"],
            language="taglish",
            country=Country.SA,
        )
        [entry] = payload["verdicts"]
        assert entry["verdict"] == "NOT_COVERED"
        assert delta is None
        routing = entry["routing"]
        assert routing == mwo_routing(Country.SA)
        # The rows are the immutable directory's, channel-tagged and
        # dialability-filtered for her country — never generated.
        assert routing["rows"] == office_directory_rows(Country.SA)
        mwo_rows = [
            row
            for row in routing["rows"]
            if row["channel"] == Channel.MWO.value
        ]
        assert mwo_rows, "an SA user must get her MWO rows"
        # Never a bare refusal: the fixed message routes and its number
        # is interpolated from a directory row, not generated.
        assert "MWO" in entry["message"]
        named = mwo_rows[0]
        assert named["phone"] in entry["message"]

    def test_not_covered_for_unknown_country_still_routes(self):
        # UNKNOWN country fails closed: nothing is dialable (the
        # directory drops what it cannot verify from where she is), so
        # the routing ships the Manila-relay row and the message routes
        # through the DMW directory instead of naming a number.
        payload, _ = debunk_claims(["hindi ko alam kung totoo ito"],
                                   language="en", country=Country.UNKNOWN)
        [entry] = payload["verdicts"]
        assert entry["verdict"] == "NOT_COVERED"
        rows = entry["routing"]["rows"]
        assert rows, "UNKNOWN still gets the Manila-relay rows"
        assert all(row["channel"] != Channel.LOCAL_POLICE.value for row in rows)
        assert all(row["dial_mode"] == "manila_relay" for row in rows)
        # Never a bare refusal, and never a number she cannot dial
        # presented as if she could: the message routes via the official
        # DMW directory and flags the listed numbers as PH-relay.
        assert "MWO" in entry["message"]
        assert "dmw.gov.ph" in entry["message"]
        assert "Philippines" in entry["message"]

    def test_a_true_verdict_confirms_and_writes_nothing_to_the_case(self):
        payload, delta = debunk_claims(
            ["if I withdraw my complaint I can't refile for 90 days"],
            language="en",
        )
        [entry] = payload["verdicts"]
        assert entry["verdict"] == "TRUE"
        assert "cannot be refiled for 90 days" in entry["rebuttal"]
        assert delta is None

    def test_verdicts_preserve_input_order_across_mixed_claims(self):
        claims = [
            "may utang pa ako sa placement fee",
            "sabi nila makukulong daw ako kapag tumakas ako",
            "kailangan ko raw ng NOC",
        ]
        payload, delta = debunk_claims(claims, language="tl", country=Country.QA)
        verdicts = [v["verdict"] for v in payload["verdicts"]]
        assert verdicts == ["FALSE", "NOT_COVERED", "FALSE"]
        assert [v["claim"] for v in payload["verdicts"]] == claims
        assert set(delta["claims"]) == {
            "debunked_placement_fee_debt",
            "debunked_noc_required_qatar",
        }

    def test_jurisdiction_scoped_template_asserts_only_where_it_applies(self):
        # The NOC entry is false IN QATAR. For a Saudi or unknown-country
        # user the same claim fails closed to NOT_COVERED and routes —
        # never a FALSE the corpus cannot stand behind there.
        claim = ["kailangan ko raw ng NOC para makalipat ng amo"]
        qa_payload, qa_delta = debunk_claims(claim, "tl", Country.QA)
        assert qa_payload["verdicts"][0]["verdict"] == "FALSE"
        assert "debunked_noc_required_qatar" in qa_delta["claims"]
        for country in (Country.SA, Country.UNKNOWN):
            payload, delta = debunk_claims(claim, "tl", country)
            [entry] = payload["verdicts"]
            assert entry["verdict"] == "NOT_COVERED"
            assert "MWO" in entry["message"]
            assert delta is None

    def test_debunk_claims_is_deterministic(self):
        claims = [c for c, _ in KNOWN_CLAIMS] + UNKNOWN_CLAIMS
        assert debunk_claims(claims, "taglish") == debunk_claims(
            claims, "taglish"
        )
