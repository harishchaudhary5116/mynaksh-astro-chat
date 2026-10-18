"""Short-term conversation context: the last N turns of one session.

In-process `deque(maxlen=N)` per session_id. Never written to the graph.
Production note: swap this class for Redis; nothing else changes.
"""
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Deque


class SessionStore(ABC):
    """The third boundary, alongside LLMClient and BrainStore."""

    @abstractmethod
    def recent(self, session_id: str) -> list[dict[str, str]]:
        """Oldest-first messages, already truncated to the turn budget."""

    @abstractmethod
    def append(self, session_id: str, role: str, content: str) -> None: ...

    @abstractmethod
    def clear(self, session_id: str) -> None: ...


class InMemorySessionStore(SessionStore):
    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self._lock = threading.RLock()
        # One turn is a user message plus our reply, hence 2x.
        self._sessions: dict[str, Deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=max_turns * 2)
        )

    def recent(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            return list(self._sessions[session_id])

    def append(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            # The deque drops the oldest message for us — that is the cap the
            # brief asks for, enforced by the data structure rather than by a
            # slice someone can forget to write.
            self._sessions[session_id].append({"role": role, "content": content})

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
