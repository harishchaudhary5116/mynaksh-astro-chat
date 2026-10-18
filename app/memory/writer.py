"""Turns extracted facts into graph writes.

Owns dedup (slug keys), attribute merging, confidence bumping on repeat
mentions, and conflict resolution by supersession rather than deletion.
"""
import logging
from dataclasses import dataclass, field

from ..brain.base import BrainError, BrainStore, slugify
from ..profile.service import ProfileService
from ..schemas import ExtractedFact, ProfileIn
from .extractor import MemoryExtractor

log = logging.getLogger(__name__)

# PROFILE facts update the :User node instead of creating a relationship.
PROFILE_FIELDS = {"name", "dob", "tob", "birth_place", "language"}


@dataclass
class WriteReport:
    """What the write path actually did — surfaced in the API for debuggability."""

    gate: str = ""
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    # The single-valued slots whose previous value this write replaced.
    superseded_slots: list[str] = field(default_factory=list)
    profile_updates: dict[str, str] = field(default_factory=dict)
    dropped: int = 0
    degraded: bool = False

    @property
    def wrote_anything(self) -> bool:
        return bool(self.created or self.updated or self.profile_updates)


class MemoryWriter:
    def __init__(
        self,
        brain: BrainStore,
        extractor: MemoryExtractor,
        profiles: ProfileService | None = None,
    ) -> None:
        self._brain = brain
        self._extractor = extractor
        self._profiles = profiles

    def remember(self, user_id: str, session_id: str, message: str) -> WriteReport:
        """Extract, then persist. Never raises: this runs after the reply is sent."""
        result = self._extractor.extract(message)
        report = WriteReport(gate=result.gate, dropped=result.dropped, degraded=result.degraded)

        for fact in result.facts:
            try:
                if fact.type == "PROFILE":
                    self._write_profile(user_id, fact, report)
                else:
                    self._write_edge(user_id, session_id, fact, report)
            except BrainError:
                # The graph is down. The user already has their answer; we log
                # and move on rather than turning a write into a 500.
                log.warning("brain unavailable, dropped fact %s for %s", fact.label, user_id)
                report.degraded = True
        return report

    # ------------------------------------------------------------------ internals

    def _write_edge(
        self, user_id: str, session_id: str, fact: ExtractedFact, report: WriteReport
    ) -> None:
        key = slugify(fact.label)
        outcome = self._brain.upsert_fact(
            user_id,
            {
                "type": fact.type,
                "key": key,
                "label": fact.label,
                "attributes": fact.attributes,
                "confidence": fact.confidence,
                "slot": fact.slot,
                "source_session": session_id,
            },
        )
        if outcome == "updated":
            report.updated.append(key)
            return
        report.created.append(key)
        if outcome == "superseded" and fact.slot:
            # The new value is live; the old one is still in the graph, stamped
            # with valid_to, so a correction is auditable rather than erased.
            report.superseded_slots.append(fact.slot)

    def _write_profile(self, user_id: str, fact: ExtractedFact, report: WriteReport) -> None:
        """Accepts {"name": "Rahul"} and the older {"field": ..., "value": ...}.

        Two shapes because two providers phrase it differently, and a profile
        update is too cheap to lose over a convention the model had to guess.
        """
        if self._profiles is None:
            return
        patch = {k: v for k, v in fact.attributes.items() if k in PROFILE_FIELDS}
        legacy_field = fact.attributes.get("field")
        if not patch and legacy_field in PROFILE_FIELDS:
            patch = {legacy_field: fact.attributes.get("value", fact.label)}
        if not patch:
            return
        try:
            # language=None so a name update cannot silently reset a language
            # preference back to the default.
            self._profiles.upsert(ProfileIn(user_id=user_id, language=None, **patch))
        except ValueError:
            log.warning("ignored malformed profile fact %r for %s", fact.attributes, user_id)
            return
        report.profile_updates.update(patch)
