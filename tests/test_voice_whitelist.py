"""After-model whitelist diff tests (issue #39, PRD #34 voice integrity).

Pure suite for ``diff_reply`` plus an HTTP-seam test where a fake model
reply carries a fabricated number after a directory tool turn: the
fabricated value must be replaced by tool-returned values and the miss
logged. Membership is a set diff over canonicalized tokens — formatting
differences neither pass a fabrication nor flag a legitimate value.
"""

import logging

from app.directory import Country, office_directory_rows
from app.guard import canonical, collect_result_values, diff_reply, value_tokens
from tests.test_chat_api import TAGLISH_EXTRACTION
from tests.test_safe_floor import ToolFakeModel, function_call, make_client, turn


def allowed(*tokens):
    return {canonical(token) for token in tokens}


class TestValueTokens:
    def test_finds_phone_like_tokens(self):
        assert value_tokens("Tumawag sa +966 11 482 0507 bukas") == [
            "+966 11 482 0507"
        ]

    def test_short_conversational_numbers_exempt(self):
        # "3 months", "1am" are conversation, not contact data.
        assert value_tokens("3 months na, umalis ako ng 1am") == []

    def test_short_codes_and_dates_found(self):
        assert value_tokens("Ang OWWA hotline ay 1348") == ["1348"]
        assert value_tokens("bago ang 2026-09-15") == ["2026-09-15"]

    def test_date_shaped_tokens_found_even_with_few_digits(self):
        # Review fix: 9/3-style and month-name dates are candidates even
        # though their digit count is below the bare-number threshold.
        assert value_tokens("ang deadline ay 9/3") == ["9/3"]
        assert value_tokens("bago ang September 15") == ["September 15"]
        assert value_tokens("sa 15 ng Setyembre") == ["15 ng Setyembre"]

    def test_plain_small_numbers_still_exempt(self):
        assert value_tokens("3 months na, 2 anak ko") == []

    def test_tagalog_existential_may_is_not_a_month(self):
        # "may 3 anak ako" is everyday Taglish, not a date.
        assert value_tokens("may 3 anak ako sa Pilipinas") == []


class TestDiffReply:
    def test_member_token_kept_verbatim(self):
        text = "Tawagan mo ang MWO sa +966 11 482 0507."
        clean, misses = diff_reply(
            text, allowed("+966 11 482 0507"), ["+966 11 482 0507"]
        )
        assert clean == text
        assert misses == []

    def test_formatting_variant_of_member_still_passes(self):
        # Canonicalization: same digits, different separators — a member.
        clean, misses = diff_reply(
            "Call +966-11-482-0507 now.",
            allowed("+966 11 482 0507"),
            ["+966 11 482 0507"],
        )
        assert misses == []

    def test_non_member_replaced_by_tool_values(self):
        clean, misses = diff_reply(
            "Tumawag ka sa 999 ngayon din.",
            allowed("+966 11 482 0507"),
            ["+966 11 482 0507"],
        )
        assert misses == ["999"]
        assert "999" not in clean
        assert "+966 11 482 0507" in clean

    def test_non_member_removed_when_no_tool_values(self):
        # Fail closed: nothing is invented to fill the hole.
        clean, misses = diff_reply("Ang deadline ay 2026-12-01.", set(), [])
        assert misses == ["2026-12-01"]
        assert "2026" not in clean

    def test_fabricated_month_name_date_caught(self):
        # Review fix: a hallucinated "September 15" deadline is a miss
        # even though it carries only two digits.
        clean, misses = diff_reply(
            "Ang deadline mo ay September 15.", set(), []
        )
        assert misses == ["September 15"]
        assert "September" not in clean

    def test_tool_returned_date_passes_in_same_format(self):
        clean, misses = diff_reply(
            "Bago ang 9/3 ang filing.", allowed("9/3"), ["9/3"]
        )
        assert misses == []

    def test_set_diff_not_regex_strip(self):
        # Two numbers, one member one not: only the non-member is touched.
        clean, misses = diff_reply(
            "MWO: +974 4483 1003. O kaya 911.",
            allowed("+974 4483 1003"),
            ["+974 4483 1003"],
        )
        assert misses == ["911"]
        assert "+974 4483 1003" in clean

    def test_user_echoed_values_pass_via_allowed_union(self):
        # The caller unions the user's own message values into `allowed`
        # — echoing her back is not fabrication.
        user_message = "500 riyals ang kulang sa sahod ko"
        allowed_set = allowed(*value_tokens(user_message))
        clean, misses = diff_reply(
            "Ang sabi mo, 500 riyals ang kulang.", allowed_set, []
        )
        assert misses == []
        assert "500" in clean

    def test_empty_reply_unchanged(self):
        assert diff_reply("", set(), []) == ("", [])


class TestCollectResultValues:
    def test_collects_from_nested_result(self):
        result = {
            "card": {
                "contacts": [
                    {"channel": "MWO", "phone": "+966 11 482 0507"},
                    {"channel": "OWWA_1348", "phone": "+63 2 1348"},
                ]
            }
        }
        values = collect_result_values(result)
        assert "+966 11 482 0507" in values
        assert "+63 2 1348" in values

    def test_deduplicates_preserving_order(self):
        result = {"a": "call 1348", "b": "again 1348"}
        assert collect_result_values(result) == ["1348"]


class TestWhitelistHttpSeam:
    """A fabricated number in a fake model reply is replaced by
    tool-returned values and the miss is logged (issue #39 acceptance)."""

    FABRICATED = "800 1234 999"

    def _run_turn(self, caplog):
        fake_model = ToolFakeModel()
        client = make_client(fake_model)
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.responses.append(function_call("office_directory", {}))
        fake_model.responses.append(
            f"Tumawag ka sa {self.FABRICATED} ngayon din."
        )
        with caplog.at_level(logging.WARNING, logger="app.guard"):
            lines = turn(client, "Sino ang matatawagan ko dito sa Saudi?")
        return lines

    def test_fabricated_number_replaced_and_logged(self, caplog):
        lines = self._run_turn(caplog)
        reply = next(line for line in lines if line["type"] == "reply")["text"]

        # The fabricated number is gone...
        assert canonical(self.FABRICATED) not in canonical(reply)
        # ...re-emitted from what the tools actually returned this turn...
        tool_phones = [
            row["phone"] for row in office_directory_rows(Country.SA)
        ]
        assert any(phone in reply for phone in tool_phones)
        # ...and the miss is logged.
        assert any(
            "VOICE_WHITELIST miss" in record.getMessage()
            for record in caplog.records
        )

    def test_tool_returned_numbers_pass_untouched(self, caplog):
        fake_model = ToolFakeModel()
        client = make_client(fake_model)
        real_phone = office_directory_rows(Country.SA)[0]["phone"]
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        fake_model.responses.append(function_call("office_directory", {}))
        fake_model.responses.append(f"Ito ang numero: {real_phone}.")
        with caplog.at_level(logging.WARNING, logger="app.guard"):
            lines = turn(client, "Sino ang matatawagan ko?")
        reply = next(line for line in lines if line["type"] == "reply")["text"]
        assert real_phone in reply
        assert not any(
            "VOICE_WHITELIST" in record.getMessage() for record in caplog.records
        )
