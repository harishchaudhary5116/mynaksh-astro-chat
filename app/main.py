"""FastAPI entrypoint."""
import logging

from fastapi import FastAPI

from .api.routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="MyNaksh — Personalized Astrology Chat",
    description="Shared Brain and memory for a conversational astrology service.",
    version="0.1.0",
)
app.include_router(router)
