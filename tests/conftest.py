"""Test wiring: FakeLLM + in-memory brain + synchronous memory writes.

No network, no Docker, no API key.

Everything is assembled by hand here rather than through `app.container`, which
is the payoff of the three interfaces: the tests exercise the real ChatService,
ContextSelector and MemoryWriter, with only the two outside edges faked.
"""
import pytest
from fastapi.testclient import TestClient

from app.brain.memory_store import InMemoryBrainStore
from app.chat.context import ContextSelector
from app.chat.service import ChatService
from app.config import Settings
from app.container import get_brain, get_chat_service, get_profiles
from app.llm.fake import FakeLLM
from app.main import app
from app.memory.extractor import MemoryExtractor
from app.memory.short_term import InMemorySessionStore
from app.memory.writer import MemoryWriter
from app.profile.service import ProfileService

RAHUL = {
    "user_id": "user-123",
    "name": "Rahul",
    "dob": "1995-08-15",
    "tob": "09:30",
    "birth_place": "Delhi",
    "language": "en",
}
# The message from the brief that should become a long-term memory.
INTRO = (
    "My name is Rahul. I was born on 15 August 1995 in Delhi. "
    "I'm planning to switch jobs next year."
)


@pytest.fixture
def settings() -> Settings:
    # async_memory_write=False so a write has happened by the time the response
    # returns and assertions do not race a background task.
    return Settings(
        llm_provider="fake",
        brain_backend="memory",
        async_memory_write=False,
        short_term_turns=6,
        max_brain_facts=5,
        min_fact_confidence=0.6,
    )


@pytest.fixture
def brain() -> InMemoryBrainStore:
    return InMemoryBrainStore()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def profiles(brain: InMemoryBrainStore) -> ProfileService:
    return ProfileService(brain)


@pytest.fixture
def service(brain, llm, profiles, settings) -> ChatService:
    return ChatService(
        llm=llm,
        sessions=InMemorySessionStore(max_turns=settings.short_term_turns),
        profiles=profiles,
        selector=ContextSelector(brain, profiles, settings.max_brain_facts),
        writer=MemoryWriter(
            brain, MemoryExtractor(llm, settings.min_fact_confidence), profiles
        ),
        settings=settings,
    )


@pytest.fixture
def client(brain, profiles, service) -> TestClient:
    app.dependency_overrides[get_chat_service] = lambda: service
    app.dependency_overrides[get_brain] = lambda: brain
    app.dependency_overrides[get_profiles] = lambda: profiles
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ------------------------------------------------------------------- helpers


@pytest.fixture
def rahul(client: TestClient) -> dict:
    """A user with a full profile, as created through the real endpoint."""
    response = client.post("/users", json=RAHUL)
    assert response.status_code == 201
    return response.json()


def say(client: TestClient, message: str, session_id: str = "session-456") -> dict:
    response = client.post(
        "/chat",
        json={"user_id": RAHUL["user_id"], "session_id": session_id, "message": message},
    )
    assert response.status_code == 200, response.text
    return response.json()


def goals(brain: InMemoryBrainStore, user_id: str = RAHUL["user_id"]) -> list[dict]:
    return [f for f in brain.dump(user_id)["facts"] if f["rel_type"] == "HAS_GOAL"]
