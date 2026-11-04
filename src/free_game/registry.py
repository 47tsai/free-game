"""Configuration-driven registry for source adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from free_game.adapters.base import Adapter
from free_game.adapters.generic import GenericAdapter, GenericSourceConfig
from free_game.adapters.steam import SteamAdapter


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_key: str
    adapter_type: str
    enabled: bool
    source_url: str
    platform: str | None = None
    feed_format: str = "auto"


AdapterFactory = Callable[[SourceDefinition], Adapter]


class SourceRegistry:
    """Validate source configuration and construct enabled adapters.

    Adapter types are explicit. Unknown types fail closed rather than silently
    falling back to the Generic adapter.
    """

    _ALLOWED_FIELDS = {
        "source_key", "adapter", "enabled", "source_url", "platform", "feed_format"
    }

    def __init__(self, definitions: list[SourceDefinition] | None = None) -> None:
        self._definitions: dict[str, SourceDefinition] = {}
        self._factories: dict[str, AdapterFactory] = {
            "generic": self._build_generic,
            "steam": self._build_steam,
        }
        for definition in definitions or []:
            self.add(definition)

    @classmethod
    def from_dict(cls, document: object) -> "SourceRegistry":
        if not isinstance(document, dict) or set(document) != {"sources"}:
            raise ValueError("source config must be an object containing only 'sources'")
        entries = document["sources"]
        if not isinstance(entries, list):
            raise ValueError("'sources' must be an array")

        definitions: list[SourceDefinition] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"sources[{index}] must be an object")
            unknown = set(entry) - cls._ALLOWED_FIELDS
            if unknown:
                raise ValueError(f"sources[{index}] has unknown fields: {', '.join(sorted(unknown))}")
            required = {"source_key", "adapter", "enabled", "source_url"}
            missing = required - set(entry)
            if missing:
                raise ValueError(f"sources[{index}] is missing fields: {', '.join(sorted(missing))}")

            source_key = entry["source_key"]
            adapter_type = entry["adapter"]
            enabled = entry["enabled"]
            source_url = entry["source_url"]
            platform = entry.get("platform")
            feed_format = entry.get("feed_format", "auto")

            if not isinstance(source_key, str) or not source_key.strip():
                raise ValueError(f"sources[{index}].source_key must be a non-empty string")
            if not isinstance(adapter_type, str) or not adapter_type.strip():
                raise ValueError(f"sources[{index}].adapter must be a non-empty string")
            if not isinstance(enabled, bool):
                raise ValueError(f"sources[{index}].enabled must be a boolean")
            if not isinstance(source_url, str):
                raise ValueError(f"sources[{index}].source_url must be a string")
            if platform is not None and (not isinstance(platform, str) or not platform.strip()):
                raise ValueError(f"sources[{index}].platform must be null or a non-empty string")
            if not isinstance(feed_format, str):
                raise ValueError(f"sources[{index}].feed_format must be a string")

            parsed = urlparse(source_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(f"sources[{index}].source_url must be an absolute HTTPS URL")
            if feed_format not in {"auto", "rss", "atom", "json"}:
                raise ValueError(f"sources[{index}].feed_format is unsupported")

            definitions.append(SourceDefinition(
                source_key=source_key,
                adapter_type=adapter_type,
                enabled=enabled,
                source_url=source_url,
                platform=platform,
                feed_format=feed_format,
            ))
        return cls(definitions)

    @classmethod
    def load(cls, path: str | Path) -> "SourceRegistry":
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load source configuration: {exc}") from exc
        return cls.from_dict(document)

    def register_factory(self, adapter_type: str, factory: AdapterFactory) -> None:
        if not adapter_type.strip():
            raise ValueError("adapter_type must not be empty")
        if adapter_type == "generic":
            raise ValueError("the built-in generic factory cannot be replaced")
        self._factories[adapter_type] = factory

    def add(self, definition: SourceDefinition) -> None:
        if definition.source_key in self._definitions:
            raise ValueError(f"duplicate source_key: {definition.source_key}")
        if not definition.source_key.strip():
            raise ValueError("source_key must not be empty")
        self._definitions[definition.source_key] = definition

    @property
    def definitions(self) -> tuple[SourceDefinition, ...]:
        return tuple(self._definitions.values())

    def build_enabled(self) -> tuple[Adapter, ...]:
        adapters: list[Adapter] = []
        for definition in self._definitions.values():
            if not definition.enabled:
                continue
            factory = self._factories.get(definition.adapter_type)
            if factory is None:
                raise ValueError(
                    f"no adapter factory registered for type: {definition.adapter_type}"
                )
            adapter = factory(definition)
            if adapter.source_key != definition.source_key:
                raise ValueError(
                    f"adapter source_key mismatch for {definition.source_key}"
                )
            adapters.append(adapter)
        return tuple(adapters)

    @staticmethod
    def _build_steam(definition: SourceDefinition) -> SteamAdapter:
        return SteamAdapter(
            source_key=definition.source_key,
            source_url=definition.source_url,
        )

    @staticmethod
    def _build_generic(definition: SourceDefinition) -> GenericAdapter:
        return GenericAdapter(GenericSourceConfig(
            source_key=definition.source_key,
            source_url=definition.source_url,
            platform=definition.platform,
            feed_format=definition.feed_format,
        ))
