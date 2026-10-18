"""The orchestrator — the file a reviewer opens first.

Reads top-to-bottom exactly like the flow in the brief:

    understand query -> select context -> build prompt -> generate -> update memory

Keep it under ~120 lines. Every step delegates; no business logic inline.
"""
import logging

from ..config import Settings
from ..errors import LLM_UNAVAILABLE, fallback_reply
from ..llm.base import LLMClient, LLMError
from ..llm.prompts import build_chat_system
from ..memory.short_term import SessionStore
from ..memory.writer import MemoryWriter
from ..profile.service import ProfileService
from ..schemas import ChatRequest, ChatResponse
from .context import ContextSelector, SelectedContext

log = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        llm: LLMClient,
        sessions: SessionStore,
        profiles: ProfileService,
        selector: ContextSelector,
        writer: MemoryWriter,
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._sessions = sessions
        self._profiles = profiles
        self._selector = selector
        self._writer = writer
        self._settings = settings

    def handle(self, request: ChatRequest, background=None) -> ChatResponse:
        """One turn, end to end. Never raises for anything but invalid input."""
        history = self._sessions.recent(request.session_id)

        # 1. understand the query and 2. select only the context it needs.
        selected = self._selector.select(request.user_id, request.message, history)

        # 3. build the prompt from the selected context — not the whole graph.
        system = build_chat_system(
            selected.profile_lines, selected.memory_lines, selected.missing_fields
        )
        messages = history + [{"role": "user", "content": request.message}]

        # 4. generate.
        reply, llm_failed = self._generate(system, messages, selected)

        # 5. the turn becomes short-term context for the next message.
        self._sessions.append(request.session_id, "user", request.message)
        self._sessions.append(request.session_id, "assistant", reply)

        # 6. update long-term memory, after the user already has their answer.
        self._remember(request, background)

        degraded = selected.degraded or llm_failed
        reason = LLM_UNAVAILABLE if llm_failed else selected.degraded_reason
        return ChatResponse(
            response=reply,
            user_id=request.user_id,
            session_id=request.session_id,
            context_used=selected.context_used,
            retrieval_strategy=selected.retrieval_strategy,
            degraded=degraded,
            degraded_reason=reason if degraded else None,
        )

    # ------------------------------------------------------------------ internals

    def _generate(
        self, system: str, messages: list[dict[str, str]], selected: SelectedContext
    ) -> tuple[str, bool]:
        """One retry, then a deterministic answer. Returns (reply, failed)."""
        for attempt in (1, 2):
            try:
                return self._llm.chat(system, messages), False
            except LLMError as exc:
                log.warning("chat LLM attempt %s failed: %s", attempt, exc)
        return (
            fallback_reply(
                selected.profile_lines, selected.memory_lines, selected.missing_fields
            ),
            True,
        )

    def _remember(self, request: ChatRequest, background) -> None:
        """Extraction costs a model call, so it must not sit in the user's latency.

        Background in production; synchronous in tests so assertions are simple.
        """
        args = (request.user_id, request.session_id, request.message)
        if self._settings.async_memory_write and background is not None:
            background.add_task(self._writer.remember, *args)
            return
        try:
            self._writer.remember(*args)
        except Exception:  # pragma: no cover - the writer already swallows its own
            log.exception("memory write failed for %s", request.user_id)
