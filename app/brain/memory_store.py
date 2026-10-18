"""Dict-backed implementation of BrainStore.

Same semantics as the Neo4j store, including supersession. Lets the whole app
and the full test suite run with no Docker and no database.

The shape mirrors the graph deliberately:

    _entities   the shared nodes, keyed (label, key) — one "Career Change"
                node for every user who ever mentions it
    _edges      the per-user relationships — this is where confidence, status,
                attributes and validity live, because that is what differs
                between two users pointing at the same node
"""
import threading
from datetime import datetime, timezone
from typing import Any

from .base import RELATIONSHIPS, BrainError, BrainStore


def _now() -> str:
    """UTC ISO-8601. Sorts lexicographically, which is all the ordering needs."""
    return datetime.now(timezone.utc).isoformat()


class InMemoryBrainStore(BrainStore):
    """Not thread-safe by accident: memory writes run in BackgroundTasks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[str, dict[str, Any]] = {}
        self._entities: dict[tuple[str, str], dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        self._seq = 0
        # Flipped by tests (and by nothing else) to exercise the degraded path.
        self.fail = False

    # ------------------------------------------------------------------ profile

    def upsert_profile(self, user_id: str, profile: dict[str, Any]) -> None:
        self._guard()
        with self._lock:
            stored = self._profiles.setdefault(
                user_id, {"user_id": user_id, "created_at": _now()}
            )
            # Only overwrite with values we actually have: a partial update must
            # not blank out a DOB we learned three conversations ago.
            stored.update({k: v for k, v in profile.items() if v is not None})
            stored["updated_at"] = _now()

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        self._guard()
        with self._lock:
            stored = self._profiles.get(user_id)
            return dict(stored) if stored else None

    # -------------------------------------------------------------------- facts

    def upsert_fact(self, user_id: str, fact: dict[str, Any]) -> str:
        """MERGE the shared entity node, then upsert the per-user relationship.

        Returns "created", "updated" or "superseded" so the caller can report
        honestly what the write actually did.
        """
        self._guard()
        fact_type = fact["type"]
        if fact_type not in RELATIONSHIPS:
            raise BrainError(f"unknown fact type: {fact_type}")
        rel_type, node_label = RELATIONSHIPS[fact_type]
        key = fact["key"]
        attributes = dict(fact.get("attributes") or {})
        confidence = float(fact.get("confidence", 0.5))
        slot = fact.get("slot")

        with self._lock:
            # MERGE (:Label {key}) — shared across users, this is the "shared" brain.
            node = self._entities.setdefault(
                (node_label, key), {"label": node_label, "key": key, "name": fact["label"]}
            )
            node["name"] = fact["label"]

            existing = self._active_edge(user_id, rel_type, key)
            if existing is not None:
                # Same thing said again: merge detail, nudge confidence up.
                existing["attributes"].update(attributes)
                existing["confidence"] = round(
                    min(1.0, max(existing["confidence"], confidence) + 0.05), 3
                )
                existing["mentions"] += 1
                existing["updated_at"] = _now()
                existing["source_session"] = fact.get("source_session") or existing["source_session"]
                if slot:
                    existing["slot"] = slot
                return "updated"

            outcome = "created"
            if slot:
                # A contradiction on a single-valued slot. Supersede rather than
                # delete: the old belief stays auditable with a valid_to stamp.
                for edge in self._active_edges(user_id):
                    if edge.get("slot") == slot and edge["key"] != key:
                        edge["status"] = "superseded"
                        edge["valid_to"] = _now()
                        edge["superseded_by"] = key
                        outcome = "superseded"

            self._seq += 1
            self._edges.append(
                {
                    "seq": self._seq,
                    "user_id": user_id,
                    "rel_type": rel_type,
                    "node_label": node_label,
                    "key": key,
                    "label": fact["label"],
                    "attributes": attributes,
                    "confidence": round(confidence, 3),
                    "status": "active",
                    "slot": slot,
                    "mentions": 1,
                    "source_session": fact.get("source_session"),
                    "created_at": _now(),
                    "updated_at": _now(),
                    "valid_to": None,
                }
            )
            return outcome

    def query_facts(
        self, user_id: str, rel_types: list[str] | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Active facts only, ordered by confidence DESC, updated_at DESC."""
        self._guard()
        with self._lock:
            found = [
                e for e in self._active_edges(user_id)
                if rel_types is None or e["rel_type"] in rel_types
            ]
        # confidence first, then most recently reinforced, then newest.
        found.sort(key=lambda e: (e["confidence"], e["updated_at"], e["seq"]), reverse=True)
        return [self._public(e) for e in found[:limit]]

    def dump(self, user_id: str) -> dict[str, Any]:
        """Whole subgraph as JSON — powers GET /users/{id}/brain."""
        self._guard()
        with self._lock:
            edges = [e for e in self._edges if e["user_id"] == user_id]
            return {
                "user_id": user_id,
                "profile": self.get_profile(user_id),
                "facts": [self._public(e, include_status=True) for e in edges],
            }

    def forget(self, user_id: str) -> int:
        """Delete all memory for a user. Right-to-be-forgotten."""
        self._guard()
        with self._lock:
            before = len(self._edges)
            self._edges = [e for e in self._edges if e["user_id"] != user_id]
            removed = before - len(self._edges)
            if self._profiles.pop(user_id, None) is not None:
                removed += 1
            # Shared entity nodes are left alone on purpose: they belong to
            # every user, not to this one.
            return removed

    def health(self) -> bool:
        return not self.fail

    # ------------------------------------------------------------------ internals

    def _guard(self) -> None:
        if self.fail:
            raise BrainError("in-memory brain is in simulated-failure mode")

    def _active_edges(self, user_id: str) -> list[dict[str, Any]]:
        return [
            e for e in self._edges
            if e["user_id"] == user_id and e["status"] == "active"
        ]

    def _active_edge(self, user_id: str, rel_type: str, key: str) -> dict[str, Any] | None:
        for edge in self._active_edges(user_id):
            if edge["rel_type"] == rel_type and edge["key"] == key:
                return edge
        return None

    @staticmethod
    def _public(edge: dict[str, Any], include_status: bool = False) -> dict[str, Any]:
        view = {
            "rel_type": edge["rel_type"],
            "node_label": edge["node_label"],
            "key": edge["key"],
            "label": edge["label"],
            "attributes": dict(edge["attributes"]),
            "confidence": edge["confidence"],
            "updated_at": edge["updated_at"],
        }
        if include_status:
            view.update(
                status=edge["status"],
                slot=edge["slot"],
                mentions=edge["mentions"],
                source_session=edge["source_session"],
                created_at=edge["created_at"],
                valid_to=edge["valid_to"],
                superseded_by=edge.get("superseded_by"),
            )
        return view
