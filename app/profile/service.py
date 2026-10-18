"""Profile CRUD + derived astrology attributes (sun sign from DOB)."""
from datetime import date
from typing import Any

from ..brain.base import BrainStore, slugify
from ..schemas import ProfileIn, ProfileOut
from . import zodiac

# Without these we cannot personalise, so the chat layer asks for them instead
# of inventing them. This is the brief's "missing user information" case.
REQUIRED_FOR_ASTROLOGY = ("name", "dob", "birth_place")


class ProfileService:
    """Reads and writes the :User node, and keeps HAS_ZODIAC in sync with DOB."""

    def __init__(self, brain: BrainStore) -> None:
        self._brain = brain

    # -------------------------------------------------------------------- write

    def upsert(self, profile: ProfileIn) -> ProfileOut:
        stored = profile.model_dump(exclude_none=True)
        if isinstance(stored.get("dob"), date):
            stored["dob"] = stored["dob"].isoformat()
        self._brain.upsert_profile(profile.user_id, stored)

        # The sun sign is derived, never user-supplied, so it is recomputed on
        # every write and mirrored into the graph as HAS_ZODIAC -> (:ZodiacSign).
        astro = zodiac.describe(profile.dob)
        if astro:
            self._brain.upsert_fact(
                profile.user_id,
                {
                    "type": "ZODIAC",
                    "key": slugify(astro["zodiac"]),
                    "label": astro["zodiac"],
                    "attributes": {"element": astro["element"]},
                    "confidence": 1.0,  # derived from DOB, not guessed
                    "slot": "zodiac:sun",  # one sun sign per user — a new DOB supersedes
                },
            )
        return self.get(profile.user_id) or ProfileOut(**profile.model_dump())

    # --------------------------------------------------------------------- read

    def get(self, user_id: str) -> ProfileOut | None:
        stored = self._brain.get_profile(user_id)
        if not stored:
            return None
        return self._to_out(stored)

    @staticmethod
    def _to_out(stored: dict[str, Any]) -> ProfileOut:
        fields = {k: v for k, v in stored.items() if k in ProfileIn.model_fields}
        profile = ProfileOut(**fields)
        astro = zodiac.describe(profile.dob)
        profile.zodiac = astro.get("zodiac")
        profile.element = astro.get("element")
        profile.missing_fields = [
            f for f in REQUIRED_FOR_ASTROLOGY if getattr(profile, f, None) is None
        ]
        return profile

    # ------------------------------------------------------------- for the prompt

    @staticmethod
    def prompt_lines(profile: ProfileOut | None) -> list[str]:
        """The profile channel of the context. Small, so it is always included.

        Returns bullet lines rather than a blob, so the token cost is visible
        and each line can be traced back in `context_used`.
        """
        if profile is None:
            return []
        lines: list[str] = []
        if profile.name:
            lines.append(f"Name: {profile.name}")
        if profile.dob:
            born = profile.dob.strftime("%d %B %Y")
            where = f" in {profile.birth_place}" if profile.birth_place else ""
            when = f" at {profile.tob}" if profile.tob else ""
            lines.append(f"Born: {born}{when}{where}")
        if profile.zodiac:
            traits = zodiac.traits(profile.zodiac)
            lines.append(f"Sun sign: {profile.zodiac} ({profile.element}) — {traits}")
        if profile.language and profile.language != "en":
            lines.append(f"Preferred language: {profile.language}")
        return lines
