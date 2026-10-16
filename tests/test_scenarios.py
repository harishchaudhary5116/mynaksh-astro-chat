"""The scenarios the brief asks for, one test each.

Each test is named after the case it covers so the reviewer can map the file
to section 8 of the assignment at a glance.
"""
import pytest

pytestmark = pytest.mark.skip(reason="scaffold — implement during the build")


def test_01_new_user_has_no_memory_yet():
    """New user: answers fine, context_used is profile only."""


def test_02_creates_long_term_memory():
    """'I'm planning to switch jobs next year' -> HAS_GOAL career-change, target_year 2027."""


def test_03_retrieves_memory():
    """A career question pulls the stored goal into context_used."""


def test_04_follow_up_uses_short_term_only():
    """'Why do you say that?' answers from recent turns; the graph is never queried."""


def test_05_new_session_recalls_previous_information():
    """Different session_id, same user -> the goal is still found."""


def test_06_irrelevant_message_is_not_stored():
    """Chit-chat passes through the gate and writes nothing to the graph."""


def test_07_user_corrects_existing_information():
    """A contradiction supersedes the old fact instead of deleting it."""


def test_08_missing_profile_information():
    """No DOB -> no crash, no invented data, asks for what is missing."""


def test_09_llm_failure_degrades_gracefully():
    """Provider raises -> 200 with a fallback reply and degraded=true."""


def test_10_brain_failure_degrades_gracefully():
    """Graph store raises -> answers from profile + short-term only."""
