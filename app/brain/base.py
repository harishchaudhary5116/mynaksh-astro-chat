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
