"""Conservative fallback adapter for configured RSS/Atom and JSON feeds."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

from free_game.adapters.base import NormalizedCandidate, SourceObservation


@dataclass(frozen=True, slots=True)
class GenericSourceConfig:
    source_key: str
    source_url: str
    platform: str | None = None
    feed_format: str = "auto"
    parser_version: str = "1"
    max_excerpt_chars: int = 2_000

    def __post_init__(self) -> None:
        if not self.source_key.strip():
            raise ValueError("source_key must not be empty")
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTPS URL")
        if self.feed_format not in {"auto", "rss", "atom", "json"}:
            raise ValueError("feed_format must be auto, rss, atom, or json")
        if self.max_excerpt_chars < 0:
            raise ValueError("max_excerpt_chars must be non-negative")


class GenericAdapter:
    """Parse predictable feed formats; never claims that a candidate is verified.

    Network fetching and persistence are intentionally outside this class so callers
    can apply shared timeouts, retries, provenance storage, and verification policy.
    """

    def __init__(self, config: GenericSourceConfig) -> None:
        self.config = config
        self.source_key = config.source_key

    def parse(self, payload: bytes | str) -> list[SourceObservation]:
        text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
        stripped = text.lstrip()
        fmt = self.config.feed_format
        if fmt == "auto":
            fmt = "json" if stripped.startswith("{") or stripped.startswith("[") else "rss"
        if fmt == "json":
            return self._parse_json(text)
        return self._parse_xml(text, expected=fmt)

    def normalize(
        self,
        observations: list[SourceObservation],
    ) -> list[NormalizedCandidate]:
        candidates: list[NormalizedCandidate] = []
        for item in observations:
            title = (item.raw_title or "").strip()
            warnings = list(item.warnings)
            if not title:
                warnings.append("missing_title")
                continue
            candidates.append(
                NormalizedCandidate(
                    source_key=item.source_key,
                    platform=self.config.platform,
                    external_product_id=None,
                    title=title,
                    product_url=item.source_url,
                    observed_at=item.observed_at,
                    verification_status="candidate",
                    source_external_id=item.external_id,
                    warnings=tuple(warnings),
                )
            )
        return candidates

    def _parse_json(self, payload: str) -> list[SourceObservation]:
        try:
            document: Any = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON feed: {exc.msg}") from exc
        if isinstance(document, dict):
            items = document.get("items")
        elif isinstance(document, list):
            items = document
        else:
            items = None
        if not isinstance(items, list):
            raise ValueError("JSON feed must be an array or contain an 'items' array")

        observed_at = datetime.now(timezone.utc)
        results: list[SourceObservation] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            title = self._first_string(item, "title", "name")
            link = self._first_string(item, "url", "external_url", "link")
            description = self._first_string(item, "content_text", "summary", "description")
            external_id = self._first_string(item, "id", "guid") or (link or f"item-{index}")
            results.append(self._observation(external_id, link, title, description, observed_at, item))
        return results

    def _parse_xml(self, payload: str, *, expected: str) -> list[SourceObservation]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ValueError(f"invalid XML feed: {exc}") from exc
        root_name = self._local_name(root.tag).lower()
        if expected == "rss" and root_name not in {"rss", "rdf"}:
            raise ValueError("expected an RSS/RDF document")
        if expected == "atom" and root_name != "feed":
            raise ValueError("expected an Atom feed")

        observed_at = datetime.now(timezone.utc)
        nodes = [node for node in root.iter() if self._local_name(node.tag).lower() in {"item", "entry"}]
        results: list[SourceObservation] = []
        for index, node in enumerate(nodes):
            values: dict[str, str] = {}
            links: list[str] = []
            for child in list(node):
                name = self._local_name(child.tag).lower()
                value = (child.text or "").strip()
                if name == "link":
                    href = child.attrib.get("href")
                    if href:
                        links.append(href.strip())
                    elif value:
                        links.append(value)
                elif value:
                    values.setdefault(name, value)
            title = values.get("title")
            link = links[0] if links else None
            external_id = values.get("guid") or values.get("id") or link or f"item-{index}"
            description = values.get("description") or values.get("summary") or values.get("content")
            results.append(self._observation(external_id, link, title, description, observed_at, values))
        return results

    def _observation(
        self,
        external_id: str | None,
        link: str | None,
        title: str | None,
        description: str | None,
        observed_at: datetime,
        raw: Any,
    ) -> SourceObservation:
        warnings: list[str] = []
        if not title:
            warnings.append("missing_title")
        if link and urlparse(link).scheme not in {"http", "https"}:
            warnings.append("unsupported_link_scheme")
            link = None
        excerpt = json.dumps(raw, ensure_ascii=False, default=str)[: self.config.max_excerpt_chars]
        return SourceObservation(
            source_key=self.source_key,
            external_id=external_id,
            observed_at=observed_at,
            source_url=link,
            raw_title=title,
            raw_description=description,
            raw_data_excerpt=excerpt,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _first_string(item: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].split(":")[-1]
