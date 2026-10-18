"""Context selection — the step the brief cares most about.

Three channels, assembled per message:

  profile      always (small, and almost always relevant)
  short-term   last N turns of this session
  long-term    up to K facts from the Shared Brain, chosen by query intent

The rule that saves the most tokens: a follow-up like "Why do you say that?"
is answered from the recent turns alone and never touches the graph.
"""
from dataclasses import dataclass, field

from ..brain.base import DEFAULT_REL_TYPES, BrainError, BrainStore
from ..llm.prompts import fact_line
from ..profile.service import ProfileService
from ..schemas import ProfileOut

# Openers that signal "about what you just said" rather than a new topic.
FOLLOWUP_OPENERS = (
    "why", "how come", "what about", "what do you mean", "and ", "so ",
    "really", "explain", "tell me more", "elaborate", "says who", "how so",
)
FOLLOWUP_MAX_WORDS = 6
# Words that only mean something if you read the previous turn.
REFERENTIAL = {"that", "this", "it", "those", "these", "them", "they"}

# Query intent -> which relationship types to traverse. Rules first because
# they are free and cover the common asks; a miss falls back to a broad query.
TOPIC_RULES: list[tuple[tuple[str, ...], list[str], str]] = [
    (
        ("remember", "recall", "know about me", "told you", "about my"),
        DEFAULT_REL_TYPES,
        "recall",
    ),
    (
        ("career", "job", "work", "promotion", "office", "salary", "interview",
         "business", "startup", "profession"),
        ["HAS_GOAL", "FOCUSES_ON", "INTERESTED_IN"],
        "career",
    ),
    (
        ("marriage", "wedding", "partner", "love", "relationship", "spouse"),
        ["FOCUSES_ON", "HAS_GOAL", "REMEMBERS"],
        "relationships",
    ),
    (
        ("language", "hindi", "english", "tamil", "speak"),
        ["PREFERS"],
        "preference",
    ),
    (
        ("health", "money", "finance", "study", "exam", "travel", "family", "home"),
        ["FOCUSES_ON", "HAS_GOAL", "REMEMBERS"],
        "life_area",
    ),
]

# Prefix used in `context_used`, so the caller sees what kind of fact was used.
_LABELS = {
    "HAS_GOAL": "goal", "INTERESTED_IN": "interest", "PREFERS": "preference",
    "FOCUSES_ON": "life_area", "REMEMBERS": "memory", "HAS_ZODIAC": "zodiac",
}


@dataclass
class SelectedContext:
    profile: ProfileOut | None = None
    profile_lines: list[str] = field(default_factory=list)
    memory_lines: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    context_used: list[str] = field(default_factory=list)
    retrieval_strategy: str = "none"
    missing_fields: list[str] = field(default_factory=list)
    degraded: bool = False
    degraded_reason: str | None = None


def classify(message: str, has_history: bool) -> tuple[list[str] | None, str]:
    """Return (relationship types to query, intent name).

    `None` for the types means "do not query the graph at all".
    """
    text = message.lower().strip()
    for triggers, rel_types, intent in TOPIC_RULES:
        if any(t in text for t in triggers):
            return rel_types, intent

    # No topic matched. If it also looks like a follow-up and there is history
    # to follow up on, the recent turns are the whole answer.
    words = text.replace("?", " ").replace(".", " ").replace("!", " ").split()
    # A follow-up either opens like one, is a two-word nudge, or points back
    # with a bare "that"/"it". Length alone is not enough: "Should I wear blue
    # on Tuesday?" is short and still a brand-new question.
    looks_like_followup = (
        text.startswith(FOLLOWUP_OPENERS)
        or len(words) <= 3
        or (bool(set(words) & REFERENTIAL) and len(words) <= FOLLOWUP_MAX_WORDS)
    )
    if looks_like_followup and has_history:
        return None, "follow_up"
    return DEFAULT_REL_TYPES, "broad"


class ContextSelector:
    def __init__(
        self,
        brain: BrainStore,
        profiles: ProfileService,
        max_facts: int = 5,
    ) -> None:
        self._brain = brain
        self._profiles = profiles
        self.max_facts = max_facts

    def select(
        self, user_id: str, message: str, history: list[dict[str, str]]
    ) -> SelectedContext:
        selected = SelectedContext(history=history)

        # --- channel 1: profile -------------------------------------------
        try:
            selected.profile = self._profiles.get(user_id)
        except BrainError:
            selected.degraded = True
            selected.degraded_reason = "shared_brain_unavailable"

        if selected.profile is not None:
            selected.profile_lines = self._profiles.prompt_lines(selected.profile)
            selected.missing_fields = selected.profile.missing_fields
            if selected.profile_lines:
                selected.context_used.append("user_profile")

        # --- channel 2: short-term ----------------------------------------
        if history:
            selected.context_used.append("short_term_context")

        # --- channel 3: long-term -----------------------------------------
        rel_types, intent = classify(message, has_history=bool(history))
        if rel_types is None:
            selected.retrieval_strategy = "short_term_only"
            return selected

        if selected.degraded:
            # Brain is down: answer from profile + short-term and say so.
            selected.retrieval_strategy = f"graph:{intent}:unavailable"
            return selected

        try:
            facts = self._brain.query_facts(user_id, rel_types, limit=self.max_facts)
        except BrainError:
            selected.degraded = True
            selected.degraded_reason = "shared_brain_unavailable"
            selected.retrieval_strategy = f"graph:{intent}:unavailable"
            return selected

        selected.memory_lines = [fact_line(f) for f in facts]
        selected.context_used.extend(
            f"{_LABELS.get(f['rel_type'], f['rel_type'].lower())}:{f['key']}" for f in facts
        )
        selected.retrieval_strategy = f"graph:{intent}" if facts else f"graph:{intent}:empty"
        return selected
