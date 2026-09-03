"""Immutable directory tests (issue #39): key resolution, dialability
filtering, immutability, and source discipline — every entry must carry
a source, and no entry may carry LOCAL_POLICE."""

import pytest
import pydantic

from app.directory import (
    _ENTRIES,
    Channel,
    Country,
    HOST_COUNTRIES,
    office_directory_rows,
    resolve_case_country,
    resolve_country,
    resolve_keys,
)


class TestTableDiscipline:
    def test_table_is_nonempty(self):
        assert _ENTRIES

    def test_no_entry_carries_local_police(self):
        assert all(e.channel is not Channel.LOCAL_POLICE for e in _ENTRIES)

    def test_every_entry_has_a_source(self):
        for entry in _ENTRIES:
            assert entry.source_url.startswith("http"), entry.key

    def test_every_entry_is_frozen(self):
        with pytest.raises(pydantic.ValidationError):
            _ENTRIES[0].phone_e164 = "+1 555 0100"

    def test_keys_are_unique(self):
        keys = [entry.key for entry in _ENTRIES]
        assert len(keys) == len(set(keys))

    def test_ph_short_codes_not_dialable_from_any_gulf_country(self):
        for entry in _ENTRIES:
            if entry.ph_relay:
                assert not (entry.dialable_from & HOST_COUNTRIES), entry.key


class TestKeyResolution:
    def test_unknown_key_dropped_never_guessed(self):
        assert resolve_keys(["definitely_not_a_key"], Country.SA) == []

    def test_action_card_keys_resolve_server_side(self):
        rows = office_directory_rows(Country.SA)
        keys = [row["key"] for row in rows]
        resolved = resolve_keys(keys, Country.SA)
        assert [row["key"] for row in resolved] == keys

    def test_number_strings_are_not_keys(self):
        rows = office_directory_rows(Country.SA)
        phone = rows[0]["phone"]
        assert resolve_keys([phone], Country.SA) == []

    def test_undialable_non_relay_number_is_dropped_not_rendered(self):
        # A Gulf MWO number requested for a user in a different country
        # must not render as if she could dial it locally.
        sa_rows = office_directory_rows(Country.SA)
        mwo_keys = [
            row["key"] for row in sa_rows if row["channel"] == Channel.MWO.value
        ]
        assert mwo_keys
        for row in resolve_keys(mwo_keys, Country.SA):
            assert row["dial_mode"] == "dialable"


class TestDirectoryRows:
    @pytest.mark.parametrize("country", sorted(HOST_COUNTRIES, key=lambda c: c.value))
    def test_gulf_user_gets_mwo_and_relay_rows(self, country):
        rows = office_directory_rows(country)
        channels = {row["channel"] for row in rows}
        assert Channel.MWO.value in channels
        assert Channel.OWWA_1348.value in channels

    def test_manila_relay_rows_are_labelled(self):
        rows = office_directory_rows(Country.SA)
        relay = [row for row in rows if row["dial_mode"] == "manila_relay"]
        assert relay
        for row in relay:
            assert "Manila" in row["note"] or "Pilipinas" in row["note"]

    def test_unknown_country_rows_have_no_host_specific_offices(self):
        rows = office_directory_rows(Country.UNKNOWN)
        assert rows
        assert all(row["channel"] != Channel.MWO.value for row in rows)


class TestCountryResolution:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Saudi Arabia", Country.SA),
            ("nasa riyadh ako", Country.SA),
            ("KSA", Country.SA),
            ("Qatar", Country.QA),
            ("doha", Country.QA),
            ("Kuwait", Country.KW),
            ("UAE", Country.AE),
            ("Dubai po", Country.AE),
            ("Bahrain", Country.UNKNOWN),
            ("", Country.UNKNOWN),
            (None, Country.UNKNOWN),
        ],
    )
    def test_resolve_country(self, text, expected):
        assert resolve_country(text) is expected

    def test_case_country_reads_the_claim_value(self):
        case = {"claims": {"country": {"value": "Qatar", "source": "user"}}}
        assert resolve_case_country(case) is Country.QA

    def test_no_case_or_malformed_claim_is_unknown(self):
        assert resolve_case_country(None) is Country.UNKNOWN
        assert resolve_case_country({}) is Country.UNKNOWN
        assert (
            resolve_case_country({"claims": {"country": "Saudi"}})
            is Country.UNKNOWN
        )
