"""FastAPI entrypoint."""
from fastapi import FastAPI

app = FastAPI(
    title="MyNaksh — Personalized Astrology Chat",
    description="Shared Brain and memory for a conversational astrology service.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# TODO: mount app.api.routes, wire settings, create graph constraints on startup.
