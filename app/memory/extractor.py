"""Decides what is worth remembering.

Stage 1 - rule gate (free): skip the LLM for pure questions, very short
messages and chit-chat. Roughly half of all turns never reach stage 2.

Stage 2 - LLM extraction (structured output): a closed vocabulary of fact types
(GOAL, INTEREST, PREFERENCE, LIFE_AREA, PROFILE, MEMORY) and an explicit
"return an empty list when nothing matters" instruction.

Stage 3 - confidence floor: drop anything below MIN_FACT_CONFIDENCE.
"""
import re
from dataclasses import dataclass, field
from datetime import date

from pydantic import ValidationError

from ..llm.base import LLMClient, LLMError
from ..llm.prompts import FACT_JSON_SCHEMA, extraction_system
from ..schemas import ExtractedFact

MIN_WORDS = 4

CHITCHAT = {
    "hi", "hello", "hey", "yo", "thanks", "thank you", "thx", "ok", "okay",
    "cool", "nice", "great", "lol", "haha", "sure", "yes", "no", "yeah", "nope",
    "good morning", "good evening", "good night", "bye", "see you", "namaste",
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class GateResult:
    """Why a message did or did not reach the extraction model."""

    passed: bool
    reason: str
    text: str = ""


@dataclass
class ExtractionResult:
    facts: list[ExtractedFact] = field(default_factory=list)
    gate: str = ""
    dropped: int = 0          # how many the confidence floor removed
    degraded: bool = False    # extraction model failed; we kept the reply anyway


def gate(message: str) -> GateResult:
    """Stage 1. Cheap, deterministic, and it rejects most turns.

    The one judgement here: a message made only of questions tells us nothing
    durable about the user, so it never costs an extraction call.
    """
    text = message.strip()
    normalised = text.lower().rstrip("!.? ")

    if normalised in CHITCHAT:
        return GateResult(False, "chit_chat")
    if len(text.split()) < MIN_WORDS:
        return GateResult(False, "too_short")

    statements = [
        s for s in _SENTENCE_SPLIT.split(text) if s.strip() and not s.strip().endswith("?")
    ]
    if not statements:
        return GateResult(False, "question_only")

    # Only the declarative part goes to the model — the question part is noise
    # for extraction and costs tokens.
    return GateResult(True, "statement", " ".join(s.strip() for s in statements))


class MemoryExtractor:
    def __init__(self, llm: LLMClient, min_confidence: float = 0.6) -> None:
        self._llm = llm
        self.min_confidence = min_confidence

    def extract(self, message: str) -> ExtractionResult:
        decision = gate(message)
        if not decision.passed:
            return ExtractionResult(gate=decision.reason)

        try:
            payload = self._llm.extract_json(
                extraction_system(date.today().isoformat()),
                decision.text,
                FACT_JSON_SCHEMA,
            )
        except LLMError:
            # Losing a memory is survivable; failing the user's reply is not.
            return ExtractionResult(gate=decision.reason, degraded=True)

        facts: list[ExtractedFact] = []
        dropped = 0
        for raw in (payload or {}).get("facts", []):
            try:
                fact = ExtractedFact(**raw)
            except (ValidationError, TypeError):
                dropped += 1  # outside the closed vocabulary — refuse it
                continue
            if fact.confidence < self.min_confidence:
                dropped += 1
                continue
            facts.append(fact)
        return ExtractionResult(facts=facts, gate=decision.reason, dropped=dropped)
