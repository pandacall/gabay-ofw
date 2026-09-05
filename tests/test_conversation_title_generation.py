"""LLM-generated Conversation titles (spec 2026-09-05-llm-conversation-titles).

Pure-function tests for the deterministic safety filter, plus the retry
orchestration against a fake async model call — no real Gemini call, no
ADK Runner involved (this path is a plain out-of-band call, per the spec).

No pytest-asyncio in this repo's dev requirements, so async bodies run via
``asyncio.run`` directly rather than adding a new test dependency.
"""

from __future__ import annotations

import asyncio

import pytest

from app.title import MAX_ATTEMPTS, generate_title, is_title_safe


class TestSafetyFilter:
    @pytest.mark.parametrize(
        "title",
        [
            "Unpaid wages, several months",
            "Passport and papers",
            "Contract dispute",
            "Agency conduct concern",
            "Job conditions",
            "General inquiry",
        ],
    )
    def test_administrative_titles_are_safe(self, title):
        assert is_title_safe(title)

    @pytest.mark.parametrize(
        "title",
        [
            "Employer assaulted me",
            "He hit me last night",
            "Threatened with harm",
            "Confined to the house",
            "Locked in the room",
            "Passport confiscated by agency",
            "Employer withheld my passport",
            "Thinking about suicide",
            "Was raped by employer",
            "Trafficked to another house",
        ],
    )
    def test_allegation_and_hard_stop_titles_are_rejected(self, title):
        assert not is_title_safe(title)

    def test_case_insensitive(self):
        assert not is_title_safe("EMPLOYER ASSAULTED ME")
        assert not is_title_safe("eMployer ASSAULTed me")

    def test_titles_with_digits_are_rejected(self):
        assert not is_title_safe("Unpaid wages for 3 months")
        assert not is_title_safe("Contract ends 2027")

    def test_overlong_titles_are_rejected(self):
        assert not is_title_safe("A" * 41)

    def test_empty_or_blank_titles_are_rejected(self):
        assert not is_title_safe("")
        assert not is_title_safe("   ")


class TestGenerateTitleRetryLoop:
    def test_accepts_a_safe_first_attempt(self):
        calls = []

        async def call_model(prompt: str) -> str:
            calls.append(prompt)
            return "Unpaid wages, several months"

        title = asyncio.run(
            generate_title(user_text="hi", reply_text="hi back", call_model=call_model)
        )
        assert title == "Unpaid wages, several months"
        assert len(calls) == 1

    def test_retries_after_a_blocked_attempt_then_accepts(self):
        outputs = iter(["Employer assaulted me", "Unpaid wages"])

        async def call_model(prompt: str) -> str:
            return next(outputs)

        title = asyncio.run(
            generate_title(user_text="hi", reply_text="hi back", call_model=call_model)
        )
        assert title == "Unpaid wages"

    def test_falls_back_to_none_after_exhausting_all_attempts(self):
        calls = []

        async def call_model(prompt: str) -> str:
            calls.append(prompt)
            return "Employer assaulted me"

        title = asyncio.run(
            generate_title(user_text="hi", reply_text="hi back", call_model=call_model)
        )
        assert title is None
        assert len(calls) == MAX_ATTEMPTS

    def test_a_retry_prompt_does_not_echo_the_blocked_term_back(self):
        prompts = []

        async def call_model(prompt: str) -> str:
            prompts.append(prompt)
            return "Employer assaulted me" if len(prompts) == 1 else "General inquiry"

        asyncio.run(
            generate_title(user_text="hi", reply_text="hi back", call_model=call_model)
        )
        assert len(prompts) == 2
        assert "assaulted" not in prompts[1].lower()

    def test_model_errors_count_as_attempts_and_fall_back_to_none(self):
        calls = []

        async def call_model(prompt: str) -> str:
            calls.append(prompt)
            raise RuntimeError("boom")

        title = asyncio.run(
            generate_title(user_text="hi", reply_text="hi back", call_model=call_model)
        )
        assert title is None
        assert len(calls) == MAX_ATTEMPTS

    def test_error_then_safe_attempt_still_succeeds(self):
        outputs = iter([RuntimeError("boom"), "Unpaid wages"])

        async def call_model(prompt: str) -> str:
            value = next(outputs)
            if isinstance(value, Exception):
                raise value
            return value

        title = asyncio.run(
            generate_title(user_text="hi", reply_text="hi back", call_model=call_model)
        )
        assert title == "Unpaid wages"
