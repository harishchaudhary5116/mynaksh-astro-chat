"""Composition root: the one place that decides which implementation is used.

Every object below is built from Settings alone. Tests never call this module —
they build the same objects with fakes and override the FastAPI dependencies,
which is the whole point of having the three interfaces.
"""
import logging
from functools import lru_cache

from .brain.base import BrainStore
from .brain.memory_store import InMemoryBrainStore
from .chat.context import ContextSelector
from .chat.service import ChatService
from .config import Settings, get_settings
from .llm.base import LLMClient
from .llm.fake import FakeLLM
from .memory.extractor import MemoryExtractor
from .memory.short_term import InMemorySessionStore, SessionStore
from .memory.writer import MemoryWriter
from .profile.service import ProfileService

log = logging.getLogger(__name__)


@lru_cache
def get_brain() -> BrainStore:
    settings = get_settings()
    if settings.brain_backend == "neo4j":
        try:
            from .brain.neo4j_store import Neo4jBrainStore  # noqa: F401

            return Neo4jBrainStore(
                settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password
            )
        except ImportError:
            # Not built yet. Degrade loudly to the in-memory brain rather than
            # refusing to boot — same interface, same semantics, no persistence.
            log.warning(
                "BRAIN_BACKEND=neo4j but the Neo4j store is unavailable; "
                "falling back to the in-memory Shared Brain (not persistent)."
            )
    return InMemoryBrainStore()


@lru_cache
def get_llm() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "gemini":
        from .llm.gemini_client import GeminiLLM

        return GeminiLLM(settings)
    if settings.llm_provider == "anthropic":
        try:
            from .llm.anthropic_client import AnthropicLLM  # noqa: F401

            return AnthropicLLM(settings)
        except ImportError:
            log.warning(
                "LLM_PROVIDER=anthropic but the client is unavailable; "
                "falling back to the scripted FakeLLM."
            )
    return FakeLLM()


@lru_cache
def get_sessions() -> SessionStore:
    return InMemorySessionStore(max_turns=get_settings().short_term_turns)


@lru_cache
def get_profiles() -> ProfileService:
    return ProfileService(get_brain())


@lru_cache
def get_chat_service() -> ChatService:
    settings: Settings = get_settings()
    brain, llm, profiles = get_brain(), get_llm(), get_profiles()
    extractor = MemoryExtractor(llm, settings.min_fact_confidence)
    return ChatService(
        llm=llm,
        sessions=get_sessions(),
        profiles=profiles,
        selector=ContextSelector(brain, profiles, settings.max_brain_facts),
        writer=MemoryWriter(brain, extractor, profiles),
        settings=settings,
    )
