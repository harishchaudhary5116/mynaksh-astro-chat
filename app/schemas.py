"""Pydantic request/response models.

Validation here is what gives us the brief's "invalid input" handling for free:
a bad body never reaches the service layer, it returns 422.

ChatResponse extends the brief's shape with `retrieval_strategy` and `degraded`
(the brief allows extending the format where useful).
"""
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# The closed vocabulary of things we are willing to remember. Anything the
# extractor returns outside this list is dropped, which is what stops the
# Shared Brain filling up with free-text junk.
FactType = Literal["GOAL", "INTEREST", "PREFERENCE", "LIFE_AREA", "MEMORY", "PROFILE"]


def _non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


# --------------------------------------------------------------------------- chat


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)

    _strip = field_validator("user_id", "session_id", "message")(_non_blank)


class ChatResponse(BaseModel):
    response: str
    user_id: str
    session_id: str
    # Truthful list of what actually went into the prompt — never hardcoded.
    context_used: list[str] = Field(default_factory=list)
    # How that context was chosen: profile_only | short_term_only | graph:<intent>
    retrieval_strategy: str
    degraded: bool = False
    degraded_reason: str | None = None


# ------------------------------------------------------------------------ profile


class ProfileIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=120)
    dob: date | None = None
    tob: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    birth_place: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default="en", max_length=32)

    _strip_user_id = field_validator("user_id")(_non_blank)


class ProfileOut(ProfileIn):
    """Profile as stored, plus the stubbed astrology derived from it."""

    zodiac: str | None = None
    element: str | None = None
    # Drives the brief's "missing user information" case: we ask instead of inventing.
    missing_fields: list[str] = Field(default_factory=list)


# -------------------------------------------------------------------------- facts


class ExtractedFact(BaseModel):
    """One candidate long-term memory, as returned by the extractor."""

    type: FactType
    label: str = Field(min_length=1, max_length=160)
    attributes: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    # Facts sharing a slot are mutually exclusive for one user, so a new one
    # supersedes the old instead of piling up. e.g. "preference:language".
    slot: str | None = Field(default=None, max_length=64)

    _strip_label = field_validator("label")(_non_blank)


class BrainDump(BaseModel):
    """GET /users/{id}/brain — the Shared Brain made inspectable without Neo4j."""

    user_id: str
    profile: dict[str, Any] | None = None
    facts: list[dict[str, Any]] = Field(default_factory=list)
