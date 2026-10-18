"""The scenarios the brief asks for, one test each.

Each test is named after the case it covers so the reviewer can map the file
to section 8 of the assignment at a glance.
"""
from datetime import date

import pytest

from app.errors import BRAIN_UNAVAILABLE, LLM_UNAVAILABLE
from app.llm.prompts import MEMORY_HEADER, MISSING_HEADER

from .conftest import INTRO, goals, say

def test_01_new_user_has_no_memory_yet(client, brain, rahul):
    """New user: answers fine, context_used is profile only."""
    answer = say(client, "Hello, I would like some guidance today please")

    assert answer["response"]
    assert answer["context_used"] == ["user_profile"]
    # The graph was queried and came back empty — not skipped, and not faked.
    assert answer["retrieval_strategy"] == "graph:broad:empty"
    assert answer["degraded"] is False
    assert goals(brain) == []


def test_02_creates_long_term_memory(client, brain, rahul):
    """'I'm planning to switch jobs next year' -> HAS_GOAL career-change, target_year 2027."""
    answer = say(client, INTRO)

    # Selection runs before the write, so this turn cannot yet see its own goal.
    assert answer["context_used"] == ["user_profile"]

    stored = goals(brain)
    assert len(stored) == 1
    goal = stored[0]
    assert goal["key"] == "career-change"
    assert goal["status"] == "active"
    assert goal["attributes"]["target_year"] == str(date.today().year + 1)
    assert goal["source_session"] == "session-456"


def test_03_retrieves_memory(client, brain, llm, rahul):
    """A career question pulls the stored goal into context_used."""
    say(client, INTRO)
    answer = say(client, "What should I focus on for my career?")

    assert "goal:career-change" in answer["context_used"]
    assert "user_profile" in answer["context_used"]
    assert answer["retrieval_strategy"] == "graph:career"

    # ...and it actually reached the prompt, not just the response envelope.
    system = [c for c in llm.calls if c[0] == "chat"][-1][1]
    assert "Career Change" in system

    # The budget held: the memory section carries at most MAX_BRAIN_FACTS bullets.
    memory_block = system.split(MEMORY_HEADER)[1]
    bullets = [l for l in memory_block.splitlines() if l.startswith("- ")]
    assert 0 < len(bullets) <= 5


def test_04_follow_up_uses_short_term_only(client, brain, rahul):
    """'Why do you say that?' answers from recent turns; the graph is never queried."""
    say(client, INTRO)
    say(client, "What should I focus on for my career?")

    calls_before = len(brain._edges)
    answer = say(client, "Why do you say that?")

    assert answer["retrieval_strategy"] == "short_term_only"
    # No fact label leaked into context_used — the graph was never read.
    assert answer["context_used"] == ["user_profile", "short_term_context"]
    assert not any(c.startswith("goal:") for c in answer["context_used"])
    # And the follow-up itself stored nothing new.
    assert len(brain._edges) == calls_before


def test_05_new_session_recalls_previous_information(client, rahul):
    """Different session_id, same user -> the goal is still found."""
    say(client, INTRO, session_id="session-456")

    answer = say(client, "What do you remember about my career goals?",
                 session_id="session-999")

    assert "goal:career-change" in answer["context_used"]
    assert answer["retrieval_strategy"] == "graph:recall"
    # A fresh session starts with an empty short-term buffer.
    assert "short_term_context" not in answer["context_used"]


def test_06_irrelevant_message_is_not_stored(client, brain, llm, rahul):
    """Chit-chat passes through the gate and writes nothing to the graph."""
    before = len(brain._edges)

    for noise in ["thanks!", "ok", "hi", "cool"]:
        say(client, noise)

    assert len(brain._edges) == before
    # The gate is the point: none of these cost an extraction call.
    assert not [c for c in llm.calls if c[0] == "extract_json"]


def test_07_user_corrects_existing_information(client, brain, rahul):
    """A contradiction supersedes the old fact instead of deleting it."""
    say(client, "I would prefer if you reply in hindi from now on")
    say(client, "Actually I prefer english from now on")

    prefs = [f for f in brain.dump("user-123")["facts"] if f["rel_type"] == "PREFERS"]
    by_key = {f["key"]: f for f in prefs}

    # The old belief is retained, stamped, and points at its replacement.
    assert by_key["hindi"]["status"] == "superseded"
    assert by_key["hindi"]["valid_to"] is not None
    assert by_key["hindi"]["superseded_by"] == "english"
    assert by_key["english"]["status"] == "active"

    # Only the live one is ever retrieved for a prompt.
    active = brain.query_facts("user-123", ["PREFERS"])
    assert [f["key"] for f in active] == ["english"]


def test_08_missing_profile_information(client, service):
    """No DOB -> no crash, no invented data, asks for what is missing."""
    client.post("/users", json={"user_id": "user-123", "name": "Asha"})

    profile = client.get("/users/user-123").json()
    assert profile["zodiac"] is None          # not guessed
    assert set(profile["missing_fields"]) == {"dob", "birth_place"}

    answer = say(client, "What does my chart say about this year?")
    assert answer["degraded"] is False        # a gap is not a failure

    # The prompt tells the model what it does NOT have, so it asks instead.
    system = [c for c in service._llm.calls if c[0] == "chat"][-1][1]
    assert MISSING_HEADER in system
    assert "dob" in system and "birth_place" in system


def test_09_llm_failure_degrades_gracefully(client, llm, rahul):
    """Provider raises -> 200 with a fallback reply and degraded=true."""
    say(client, INTRO)
    llm.fail = True

    answer = say(client, "What should I focus on for my career?")

    assert answer["degraded"] is True
    assert answer["degraded_reason"] == LLM_UNAVAILABLE
    assert answer["response"]
    # The fallback must not pretend it answered, but should prove we still
    # hold the user's context.
    assert "Career Change" in answer["response"]
    # Selection still ran and is still reported truthfully.
    assert "goal:career-change" in answer["context_used"]


def test_10_brain_failure_degrades_gracefully(client, brain, rahul):
    """Graph store raises -> answers from profile + short-term only."""
    say(client, INTRO)
    brain.fail = True

    answer = say(client, "What should I focus on for my career?")

    assert answer["degraded"] is True
    assert answer["degraded_reason"] == BRAIN_UNAVAILABLE
    assert answer["retrieval_strategy"].endswith(":unavailable")
    assert answer["response"]
    # No memory was claimed, because none could be read.
    assert not any(c.startswith("goal:") for c in answer["context_used"])
