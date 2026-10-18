"""Settings from the environment. See .env.example for every knob."""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """One typed object for every knob, so nothing reads os.environ directly."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---------- LLM ----------
    llm_provider: Literal["anthropic", "openai", "gemini", "fake"] = "gemini"
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    # Model routing: a small cheap model extracts facts, a bigger one talks to
    # the user. Both names are provider-specific, so they live in .env.
    llm_chat_model: str = "gemini-flash-latest"
    llm_extraction_model: str = "gemini-flash-lite-latest"

    # ---------- Shared Brain ----------
    brain_backend: Literal["neo4j", "memory"] = "memory"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "mynaksh123"

    # ---------- Memory tuning ----------
    # The two caps that keep the prompt small: 6 recent turns, 5 long-term facts.
    short_term_turns: int = Field(default=6, ge=1, le=50)
    max_brain_facts: int = Field(default=5, ge=1, le=50)
    min_fact_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    async_memory_write: bool = True


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is parsed once per process."""
    return Settings()
