"""Shared Brain boundary.

Two implementations: `neo4j_store` (real) and `memory_store` (no infrastructure,
used by tests and by reviewers without Docker). Same interface, so the app and
the tests never know which one is behind it.
"""
from abc import ABC, abstractmethod
from typing import Any


class BrainError(Exception):
    """Raised when the graph store is unreachable or a query fails."""


class BrainStore(ABC):
    @abstractmethod
    def upsert_profile(self, user_id: str, profile: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_profile(self, user_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def upsert_fact(self, user_id: str, fact: dict[str, Any]) -> str:
        """MERGE the shared entity node, then upsert the per-user relationship.

        Same (user, rel_type, key) -> merge attributes and bump confidence.
        Contradiction on a single-valued type -> supersede the old relationship
        (status='superseded', valid_to=now) and create a new one.
        """

    @abstractmethod
    def query_facts(
        self, user_id: str, rel_types: list[str] | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Active facts only, ordered by confidence DESC, updated_at DESC."""

    @abstractmethod
    def dump(self, user_id: str) -> dict[str, Any]:
        """Whole subgraph as JSON — powers GET /users/{id}/brain."""

    @abstractmethod
    def forget(self, user_id: str) -> int:
        """Delete all memory for a user. Right-to-be-forgotten."""

    @abstractmethod
    def health(self) -> bool: ...


# --------------------------------------------------------------- graph vocabulary
# Both stores share this, so the Cypher schema and the in-memory fallback can
# never drift apart. Fact type -> (relationship type, shared entity label).
RELATIONSHIPS: dict[str, tuple[str, str]] = {
    "GOAL": ("HAS_GOAL", "Goal"),
    "INTEREST": ("INTERESTED_IN", "Interest"),
    "PREFERENCE": ("PREFERS", "Preference"),
    "LIFE_AREA": ("FOCUSES_ON", "LifeArea"),
    "MEMORY": ("REMEMBERS", "Memory"),
    "ZODIAC": ("HAS_ZODIAC", "ZodiacSign"),
}

# What a broad retrieval searches. HAS_ZODIAC is deliberately excluded: the sun
# sign already rides along on the profile line, and spending one of the five
# fact slots to say it twice is exactly the waste the brief warns about.
DEFAULT_REL_TYPES: list[str] = [
    "HAS_GOAL", "INTERESTED_IN", "PREFERS", "FOCUSES_ON", "REMEMBERS",
]


def slugify(text: str) -> str:
    """Stable entity key, so 'Career Change' and 'career change' are one node.

    Dedup lives in the key: `MERGE (:Goal {key: 'career-change'})` is idempotent,
    which is what lets the same goal be mentioned five times without five nodes.
    """
    cleaned = [c.lower() if c.isalnum() else "-" for c in text.strip()]
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:80] or "unknown"
