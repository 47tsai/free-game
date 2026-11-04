"""4Gamers RSS filtering and normalization."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from free_game.adapters.base import NormalizedCandidate, SourceObservation

_FREE_GAME_RE = re.compile(r"限免|限時免費|紳士限免", re.IGNORECASE)


def _text(node, name: str) -> str | None:
    for child in list(node):
        if child.tag.rsplit("}", 1)[-1].lower() == name.lower():
            value = "".join(child.itertext()).strip()
            return value or None
    return None


class FourGamersAdapter:
    source_key = "4gamers:latest-news"

    def parse(self, payload: bytes | str) -> list[SourceObservation]:
        text = payload.decode("utf-8-sig", errors="replace") if isinstance(payload, bytes) else payload
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ValueError("invalid_4gamers_rss") from exc
        results = []
        for item in root.iter():
            if item.tag.rsplit("}", 1)[-1].lower() != "item":
                continue
            title = _text(item, "title")
            description = _text(item, "description")
            if not _FREE_GAME_RE.search((title or "") + " " + (description or "")):
                continue
            url = _text(item, "link")
            guid = _text(item, "guid") or url
            if not url or not guid:
                continue
            published = _text(item, "pubDate")
            try:
                observed_at = parsedate_to_datetime(published) if published else datetime.now(timezone.utc)
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=timezone.utc)
                observed_at = observed_at.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                observed_at = datetime.now(timezone.utc)
            results.append(SourceObservation(
                source_key=self.source_key,
                external_id=guid,
                observed_at=observed_at,
                source_url=url,
                raw_title=title,
                raw_description=description,
            ))
        return results

    def normalize(self, observations: list[SourceObservation]) -> list[NormalizedCandidate]:
        return [
            NormalizedCandidate(
                source_key=item.source_key,
                platform=None,
                external_product_id=None,
                title=(item.raw_title or "").strip(),
                product_url=item.source_url,
                observed_at=item.observed_at,
                source_external_id=item.external_id,
                article_url=item.source_url,
            )
            for item in observations
            if item.raw_title and item.raw_title.strip() and item.external_id
        ]
