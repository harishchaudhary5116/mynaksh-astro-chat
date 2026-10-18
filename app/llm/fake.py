"""Scripted LLM for tests.

Deterministic, free and offline. This is what lets all 10 scenarios run in
under two seconds with no API key.

Two behaviours matter:

  chat()         echoes the context it was given, so a test can assert that the
                 right memories reached the prompt — not just that a string
                 came back.
  extract_json() applies substring rules standing in for the extraction model,
                 covering the conversation in the brief.
"""
from datetime import date
from typing import Any, Callable

from .base import LLMClient, LLMError


def _next_year() -> str:
    return str(date.today().year + 1)


# (trigger substrings, facts to return). First match wins; order matters.
DEFAULT_SCRIPT: list[tuple[tuple[str, ...], list[dict[str, Any]]]] = [
    (
        ("switch jobs", "switching jobs", "change jobs", "new job"),
        [{
            "type": "GOAL", "label": "Career Change",
            "attributes": {"target_year": _next_year()}, "confidence": 0.9,
        }],
    ),
    (
        ("product management interview", "pm interview"),
        [{
            "type": "GOAL", "label": "Product Management Interview",
            "attributes": {"timeframe": "next month"}, "confidence": 0.9,
        }],
    ),
    (
        ("not switching", "changed my mind", "staying at my current job", "decided to stay"),
        [{
            "type": "GOAL", "label": "Stay In Current Role",
            "attributes": {}, "confidence": 0.9, "slot": "goal:career-direction",
        }],
    ),
    (
        ("in hindi", "speak hindi", "prefer hindi"),
        [{
            "type": "PREFERENCE", "label": "Hindi",
            "attributes": {"kind": "language"}, "confidence": 0.9,
            "slot": "preference:language",
        }],
    ),
    (
        ("in english", "prefer english"),
        [{
            "type": "PREFERENCE", "label": "English",
            "attributes": {"kind": "language"}, "confidence": 0.9,
            "slot": "preference:language",
        }],
    ),
    (
        ("entrepreneurship", "start my own", "startup", "own business"),
        [{"type": "INTEREST", "label": "Entrepreneurship", "attributes": {}, "confidence": 0.85}],
    ),
    (
        ("getting married", "my wedding", "marriage"),
        [{"type": "LIFE_AREA", "label": "Marriage", "attributes": {}, "confidence": 0.8}],
    ),
    (
        ("maybe someday", "i might", "not sure yet"),
        # Deliberately below MIN_FACT_CONFIDENCE: proves the floor drops things.
        [{"type": "GOAL", "label": "Vague Idea", "attributes": {}, "confidence": 0.3}],
    ),
]


class FakeLLM(LLMClient):
    """Drop-in LLMClient. `fail=True` exercises the degraded path."""

    def __init__(
        self,
        *,
        fail: bool = False,
        replies: list[str] | None = None,
        script: list[tuple[tuple[str, ...], list[dict[str, Any]]]] | None = None,
        extract_hook: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.fail = fail
        self.replies = list(replies or [])
        self.script = DEFAULT_SCRIPT if script is None else script
        self.extract_hook = extract_hook
        # Every call recorded, so tests can assert the LLM was *not* called too.
        self.calls: list[tuple[str, Any, Any]] = []

    # --------------------------------------------------------------------- chat

    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        self.calls.append(("chat", system, messages))
        if self.fail:
            raise LLMError("fake provider is unavailable")
        if self.replies:
            return self.replies.pop(0)

        question = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        known = [line[2:].strip() for line in system.splitlines() if line.startswith("- ")]
        if known:
            return f"On \"{question}\" — going by what I know ({'; '.join(known)}), here is my read."
        return f"On \"{question}\" — I do not know much about you yet, so here is a general read."

    # ------------------------------------------------------------------ extract

    def extract_json(
        self, system: str, user_text: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(("extract_json", system, user_text))
        if self.fail:
            raise LLMError("fake provider is unavailable")
        if self.extract_hook is not None:
            return {"facts": self.extract_hook(user_text)}

        text = user_text.lower()
        facts: list[dict[str, Any]] = []
        for triggers, scripted in self.script:
            if any(t in text for t in triggers):
                facts = [dict(f) for f in scripted]
                break

        # Identity details ride along with whatever else the message carried.
        if "my name is" in text:
            name = user_text.lower().split("my name is", 1)[1]
            name = name.replace(".", " ").replace(",", " ").split()[0].capitalize()
            facts.append({
                "type": "PROFILE", "label": name,
                "attributes": {"field": "name", "value": name},
                "confidence": 0.95, "slot": "profile:name",
            })
        return {"facts": facts}
