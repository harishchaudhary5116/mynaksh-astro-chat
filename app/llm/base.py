"""Provider-agnostic LLM boundary.

Everything in the app talks to this interface, so swapping Anthropic for
OpenAI/Gemini/a local model means adding one file, not rewriting the app.
"""
from abc import ABC, abstractmethod
from typing import Any


class LLMError(Exception):
    """Raised when a provider call fails after retries."""


class LLMClient(ABC):
    @abstractmethod
    def chat(self, system: str, messages: list[dict[str, str]]) -> str:
        """Generate the user-facing reply."""

    @abstractmethod
    def extract_json(self, system: str, user_text: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Return structured JSON matching `schema`.

        Use the provider's structured-output mode. Never regex-parse JSON out
        of free text, and never use forced tool_choice (400 on current models).
        """
