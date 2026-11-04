"""4Gamers RSS discovery adapter."""

from __future__ import annotations

import re

from free_game.adapters.base import NormalizedCandidate, SourceObservation
from free_game.adapters.generic import GenericAdapter, GenericSourceConfig


_FREE_GAME_RE = re.compile(r"限免|限時免費|紳士限免", re.IGNORECASE)


class FourGamersAdapter:
    """Select free-game announcements from the 4Gamers latest-news RSS feed."""

    source_key = "4gamers:latest-news"

    def __init__(self, source_url: str) -> None:
        self._feed = GenericAdapter(GenericSourceConfig(
            source_key=self.source_key,
            source_url=source_url,
            platform=None,
            feed_format="rss",
        ))

    def parse(self, payload: bytes | str) -> list[SourceObservation]:
        observations = self._feed.parse(payload)
        return [
            item for item in observations
            if _FREE_GAME_RE.search(
                f"{item.raw_title or ''} {item.raw_description or ''}"
            )
        ]

    def normalize(
        self,
        observations: list[SourceObservation],
    ) -> list[NormalizedCandidate]:
        return self._feed.normalize(observations)
