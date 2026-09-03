"""ROUTING_GUARD pure suite — CI-gating (issue #39, PRD #34).

The highest-consequence code in the system, tested property-style against
the pure enforcement core (no ADK plumbing, no infrastructure, no API
key). The most important assertions are what must NOT happen: local
police never survives under any spelling, unknown channels never survive,
UNKNOWN never widens anything, and no guard path ever returns ``{}``.
"""

import asyncio

import pytest

from app.directory import Channel, Country, resolve_country
from app.guard import (
    ALLOWED_TOOLS,
    PERMITTED_CHANNELS,
    RoutingGuardPlugin,
    filter_rows,
    filter_tool_result,
    guard_before_tool,
    permitted_for,
    refusal,
)

ALL_COUNTRIES = list(Country)
KNOWN_COUNTRIES = [Country.SA, Country.QA, Country.KW, Country.AE]

# Every spelling an argument, a row label, or a channel tag might smuggle
# local police in under. The guard never sees these — it sees the channel
# enum on the RESULT — but the fixtures prove spelling is irrelevant.
LOCAL_POLICE_SPELLINGS = [
    "LOCAL_POLICE",
    "local_police",
    "Local Police",
    "police",
    "POLICE",
    "shurta",
    "شرطة",
    "call 999",
    "kapulisan",
    "pulis",
    "Saudi police station",
    "nearest police",
]


def row(channel, label="Some office", **extra):
    return {"key": "k", "channel": channel, "label": label, **extra}


class TestLocalPoliceRefused:
    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    def test_local_police_channel_dropped_everywhere(self, country):
        kept, dropped = filter_rows([row(Channel.LOCAL_POLICE.value)], country)
        assert kept == []
        assert dropped == 1

    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    @pytest.mark.parametrize("spelling", LOCAL_POLICE_SPELLINGS)
    def test_no_spelling_of_local_police_survives(self, country, spelling):
        # A row whose channel tag is any spelling other than a permitted
        # enum member is dropped — misspellings don't widen, they narrow.
        kept, _ = filter_rows([row(spelling, label=spelling)], country)
        assert kept == []

    def test_local_police_in_no_permitted_set(self):
        for country, permitted in PERMITTED_CHANNELS.items():
            assert Channel.LOCAL_POLICE not in permitted, country

    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    def test_local_police_dropped_even_mixed_with_permitted_rows(self, country):
        rows = [
            row(Channel.EMBASSY_ATN.value),
            row(Channel.LOCAL_POLICE.value),
            row(Channel.OWWA_1348.value),
        ]
        kept, dropped = filter_rows(rows, country)
        assert dropped >= 1
        assert all(r["channel"] != Channel.LOCAL_POLICE.value for r in kept)


class TestUnknownChannelDropped:
    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    @pytest.mark.parametrize(
        "bad_channel",
        ["HOTLINE", "mwo", "", None, 42, "EMBASSY", "OWWA", "1348"],
    )
    def test_unknown_channel_tag_dropped(self, country, bad_channel):
        kept, dropped = filter_rows([row(bad_channel)], country)
        assert kept == []
        assert dropped == 1

    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    def test_row_without_channel_dropped(self, country):
        kept, _ = filter_rows([{"key": "k", "label": "no channel"}], country)
        assert kept == []

    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    def test_non_dict_row_dropped(self, country):
        kept, _ = filter_rows(["+63 2 1348", 999, None], country)
        assert kept == []


class TestUnknownCountryMostRestrictive:
    def test_unknown_blocks_all_routing_but_embassy_atn_and_1348(self):
        assert permitted_for(Country.UNKNOWN) == frozenset(
            {Channel.EMBASSY_ATN, Channel.OWWA_1348}
        )

    @pytest.mark.parametrize("country", KNOWN_COUNTRIES)
    def test_unknown_is_proper_subset_of_every_known_set(self, country):
        # UNKNOWN is more restrictive than known-dangerous, never less.
        assert permitted_for(Country.UNKNOWN) < permitted_for(country)

    def test_unmapped_country_value_gets_unknown_set(self):
        assert permitted_for(Country.PH) == permitted_for(Country.UNKNOWN)

    def test_unknown_country_filters_mwo_rows(self):
        rows = [
            row(Channel.MWO.value),
            row(Channel.EMBASSY_ATN.value),
            row(Channel.OWWA_1348.value),
            row(Channel.DMW_HOTLINE.value),
        ]
        kept, _ = filter_rows(rows, Country.UNKNOWN)
        assert {r["channel"] for r in kept} == {
            Channel.EMBASSY_ATN.value,
            Channel.OWWA_1348.value,
        }

    @pytest.mark.parametrize(
        "text",
        [None, "", "Bahrain", "Pilipinas", "the moon", "Saud1 Arab1a?"],
    )
    def test_unresolvable_country_text_is_unknown(self, text):
        assert resolve_country(text) is Country.UNKNOWN


class TestNeverEmptyDict:
    """{} from a before-tool callback short-circuits the real tool and
    breaks silently once a second callback exists (google-adk 2.8.0,
    flows/llm_flows/functions.py). Allow is None; refusal is non-empty."""

    def test_refusal_is_never_empty(self):
        assert refusal("ANY") != {}
        assert refusal("ANY")["refused"] is True

    def test_root_callback_allows_with_none_and_refuses_non_empty(self):
        class FakeTool:
            def __init__(self, name):
                self.name = name

        for name in ALLOWED_TOOLS:
            assert (
                guard_before_tool(
                    tool=FakeTool(name), args={}, tool_context=None
                )
                is None
            )
        refused = guard_before_tool(
            tool=FakeTool("some_unlisted_tool"), args={}, tool_context=None
        )
        assert refused is not None
        assert refused != {}
        assert refused["refused"] is True

    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    def test_filtered_result_is_never_empty_dict(self, country):
        filtered, _ = filter_tool_result(
            {"rows": [row(Channel.LOCAL_POLICE.value)]}, country
        )
        assert filtered != {}
        assert filtered["rows"] == []

    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    def test_malformed_result_replaced_by_refusal(self, country):
        filtered, dropped = filter_tool_result("not a dict", country)
        assert filtered != {}
        assert filtered["refused"] is True
        assert dropped == 1


class TestNeverConditionedOnFlags:
    """The guard reads country only — a Case drowning in safety flags and
    a Case with none produce identical filtering."""

    @pytest.mark.parametrize("country", ALL_COUNTRIES)
    def test_flags_are_structurally_unreachable_in_pure_core(self, country):
        rows = [
            row(Channel.MWO.value),
            row(Channel.LOCAL_POLICE.value),
            row(Channel.EMBASSY_ATN.value),
        ]
        # filter_rows takes no case at all — flags cannot reach the decision.
        kept, dropped = filter_rows(list(rows), country)
        assert all(r["channel"] != Channel.LOCAL_POLICE.value for r in kept)
        assert dropped >= 1

    @pytest.mark.parametrize(
        "flags",
        [{}, {"PHYSICAL_ASSAULT_ONGOING": {}, "CONFINED": {}}],
        ids=["no-flags", "acute-flags"],
    )
    def test_plugin_filtering_identical_with_and_without_flags(self, flags):
        class FakeTool:
            name = "office_directory"

        class FakeToolContext:
            def __init__(self, case):
                self.state = {"case": case}

        case = {
            "claims": {"country": {"value": "Saudi Arabia", "source": "user"}},
            "safety_flags": flags,
        }
        result = {
            "rows": [
                row(Channel.MWO.value),
                row(Channel.LOCAL_POLICE.value),
            ]
        }
        filtered = asyncio.run(
            RoutingGuardPlugin().after_tool_callback(
                tool=FakeTool(),
                tool_args={},
                tool_context=FakeToolContext(case),
                result=result,
            )
        )
        assert [r["channel"] for r in filtered["rows"]] == [Channel.MWO.value]
        assert filtered["guard_dropped"] == 1


class TestNestedResultsFiltered:
    def test_rows_nested_inside_card_are_filtered(self):
        result = {
            "card": {
                "type": "safe_floor",
                "contacts": [
                    row(Channel.EMBASSY_ATN.value),
                    row(Channel.LOCAL_POLICE.value),
                ],
            }
        }
        filtered, dropped = filter_tool_result(result, Country.UNKNOWN)
        assert dropped == 1
        contacts = filtered["card"]["contacts"]
        assert [r["channel"] for r in contacts] == [Channel.EMBASSY_ATN.value]

    @pytest.mark.parametrize("key", ["rows", "contacts"])
    def test_untagged_rows_under_contract_keys_are_dropped(self, key):
        # Review fix: 'rows'/'contacts' lists are contact rows by
        # contract — an entirely untagged (channel-less) list under those
        # keys is dropped, never passed through unfiltered.
        result = {key: [{"label": "Some office", "phone": "+966 555"}]}
        filtered, dropped = filter_tool_result(result, Country.SA)
        assert filtered[key] == []
        assert dropped == 1
