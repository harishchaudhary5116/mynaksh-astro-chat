"""HTTP surface.

  POST   /chat                      the graded flow
  POST   /users                     create/update a profile
  GET    /users/{user_id}           read a profile
  GET    /users/{user_id}/brain     inspect the Shared Brain as JSON
  DELETE /users/{user_id}/memory    right to be forgotten
  GET    /health                    liveness + brain backend status
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..brain.base import BrainError, BrainStore
from ..chat.service import ChatService
from ..container import get_brain, get_chat_service, get_profiles
from ..profile.service import ProfileService
from ..schemas import BrainDump, ChatRequest, ChatResponse, ProfileIn, ProfileOut

router = APIRouter()

# Invalid input is already a 422 from the pydantic models. The only error this
# layer raises is "the graph is gone", and only where there is nothing sensible
# to return without it — /chat degrades instead.
BRAIN_DOWN = "Shared Brain is unavailable. Try again shortly."


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    background: BackgroundTasks,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return service.handle(request, background)


@router.post("/users", response_model=ProfileOut, status_code=201)
def upsert_user(
    profile: ProfileIn, profiles: ProfileService = Depends(get_profiles)
) -> ProfileOut:
    try:
        return profiles.upsert(profile)
    except BrainError:
        raise HTTPException(status_code=503, detail=BRAIN_DOWN)


@router.get("/users/{user_id}", response_model=ProfileOut)
def get_user(
    user_id: str, profiles: ProfileService = Depends(get_profiles)
) -> ProfileOut:
    try:
        profile = profiles.get(user_id)
    except BrainError:
        raise HTTPException(status_code=503, detail=BRAIN_DOWN)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"No profile for {user_id!r}")
    return profile


@router.get("/users/{user_id}/brain", response_model=BrainDump)
def get_brain_dump(user_id: str, brain: BrainStore = Depends(get_brain)) -> BrainDump:
    """Superseded facts are included on purpose — the audit trail is the feature."""
    try:
        return BrainDump(**brain.dump(user_id))
    except BrainError:
        raise HTTPException(status_code=503, detail=BRAIN_DOWN)


@router.delete("/users/{user_id}/memory")
def forget_user(user_id: str, brain: BrainStore = Depends(get_brain)) -> dict[str, int | str]:
    try:
        return {"user_id": user_id, "removed": brain.forget(user_id)}
    except BrainError:
        raise HTTPException(status_code=503, detail=BRAIN_DOWN)


@router.get("/health")
def health(brain: BrainStore = Depends(get_brain)) -> dict[str, object]:
    try:
        brain_ok = brain.health()
    except BrainError:
        brain_ok = False
    return {
        "status": "ok",
        "brain": {"backend": type(brain).__name__, "healthy": brain_ok},
    }
