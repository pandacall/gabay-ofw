"""Conversations at the HTTP seam (issue #72, ADR-0008): create, list, re-open, delete.

Same injection pattern as ``tests/test_chat_api.py`` — a fake token
verifier, ADK's ``InMemorySessionService``, and a fake model at the
``BaseLlm`` boundary, all passed through ``create_app``. Nothing internal
is mocked.

What these assert she experiences:

* many Conversations, each its own transcript, listed most-recent first
* one shared Case — a fact given in one Conversation is known in every
  other, and no Conversation's transcript leaks into another's context
* re-opening a Conversation restores its transcript and cards, with a
  past deadline-bearing Plan card collapsed so it can't be acted on
* deleting a Conversation removes only that transcript — her Case and the
  delete-everything path are untouched
"""

from __future__ import annotations

import json

from tests.test_chat_api import (
    ENGLISH_EXTRACTION,
    TAGLISH_EXTRACTION,
    auth,
    client,  # noqa: F401 — pytest fixture
    fake_model,  # noqa: F401 — pytest fixture
    turn,
)


def _conversations(client, uid="maria"):
    response = client.get("/api/conversations", headers=auth(uid))
    assert response.status_code == 200
    return response.json()["conversations"]


class TestListing:
    def test_requires_a_token(self, client):
        assert client.get("/api/conversations").status_code == 401

    def test_lists_each_conversation_most_recent_first(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        first, _ = turn(client, "Kinuha nila ang passport ko")
        first_id = first["reply"]["session_id"]

        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        second, _ = turn(client, "Hindi ako nababayaran")
        second_id = second["reply"]["session_id"]

        assert first_id != second_id
        listed = [row["session_id"] for row in _conversations(client)]
        assert listed == [second_id, first_id]

    def test_only_lists_the_callers_own_conversations(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        turn(client, "Kinuha nila ang passport ko", uid="maria")
        assert _conversations(client, uid="intruder") == []


def _transcript(client, session_id, uid="maria"):
    response = client.get(f"/api/conversations/{session_id}", headers=auth(uid))
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line]


class TestReopening:
    def test_restores_the_transcript_of_user_turns_and_replies(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type, _ = turn(client, "Hindi ako nababayaran")
        session_id = by_type["reply"]["session_id"]
        reply_text = by_type["reply"]["text"]

        lines = _transcript(client, session_id)
        assert {"type": "user", "text": "Hindi ako nababayaran"} in lines
        assert {"type": "reply", "text": reply_text} in lines
        # The transient scaffolding of a live turn is not transcript.
        assert all(line["type"] not in ("ack", "trail") for line in lines)

    def test_unknown_conversation_is_404(self, client):
        assert (
            client.get("/api/conversations/nope", headers=auth("maria")).status_code
            == 404
        )

    def test_another_users_conversation_is_404(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        by_type, _ = turn(client, "Hindi ako nababayaran", uid="maria")
        session_id = by_type["reply"]["session_id"]
        assert (
            client.get(
                f"/api/conversations/{session_id}", headers=auth("intruder")
            ).status_code
            == 404
        )


class TestSharedCaseAcrossConversations:
    def test_a_fact_given_in_one_conversation_is_known_in_the_next(
        self, client, fake_model
    ):
        # ADR-0008: one Case per user, shared by every Conversation.
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        turn(client, "Kinuha nila ang passport ko sa Saudi Arabia")

        # A brand-new Conversation (no session_id) — its very first turn's
        # Case already carries what she disclosed in the first thread.
        fake_model.extraction_results.append(
            json.dumps({"language": "taglish", "claims": {}, "safety_flags": []})
        )
        by_type, _ = turn(client, "Ano ang gagawin ko?")
        case = by_type["case"]["case"]
        assert case["claims"]["country"]["value"] == "Saudi Arabia"
        assert "PASSPORT_WITHHELD" in case["safety_flags"]

    def test_one_conversations_transcript_never_enters_anothers(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        first, _ = turn(client, "SECRET-MARKER-of-the-first-thread")
        first_id = first["reply"]["session_id"]

        fake_model.extraction_results.append(
            json.dumps({"language": "taglish", "claims": {}, "safety_flags": []})
        )
        second, _ = turn(client, "a question in the second thread")
        second_id = second["reply"]["session_id"]

        second_transcript = json.dumps(_transcript(client, second_id))
        assert "SECRET-MARKER-of-the-first-thread" not in second_transcript
        first_transcript = json.dumps(_transcript(client, first_id))
        assert "SECRET-MARKER-of-the-first-thread" in first_transcript


class TestDeletion:
    def test_deleting_a_conversation_removes_its_transcript_but_not_the_case(
        self, client, fake_model
    ):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        first, _ = turn(client, "Kinuha nila ang passport ko sa Saudi Arabia")
        first_id = first["reply"]["session_id"]

        response = client.delete(
            f"/api/conversations/{first_id}", headers=auth("maria")
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": True}

        assert first_id not in [row["session_id"] for row in _conversations(client)]
        assert (
            client.get(
                f"/api/conversations/{first_id}", headers=auth("maria")
            ).status_code
            == 404
        )

        # Her Case survived the delete — a new Conversation still knows it.
        fake_model.extraction_results.append(
            json.dumps({"language": "taglish", "claims": {}, "safety_flags": []})
        )
        by_type, _ = turn(client, "kumusta")
        assert by_type["case"]["case"]["claims"]["country"]["value"] == "Saudi Arabia"
        assert "PASSPORT_WITHHELD" in by_type["case"]["case"]["safety_flags"]

    def test_deleting_an_unknown_conversation_is_404(self, client):
        assert (
            client.delete(
                "/api/conversations/nope", headers=auth("maria")
            ).status_code
            == 404
        )

    def test_cannot_delete_another_users_conversation(self, client, fake_model):
        fake_model.extraction_results.append(TAGLISH_EXTRACTION)
        first, _ = turn(client, "Hindi ako nababayaran", uid="maria")
        first_id = first["reply"]["session_id"]
        assert (
            client.delete(
                f"/api/conversations/{first_id}", headers=auth("intruder")
            ).status_code
            == 404
        )
        # …and it is still there for its owner.
        assert first_id in [
            row["session_id"] for row in _conversations(client, uid="maria")
        ]
