from __future__ import annotations

import json

import pytest

from free_game.adapters import GenericAdapter
from free_game.registry import SourceDefinition, SourceRegistry


def config_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "source_key": "unknown-shop:promotions",
        "adapter": "generic",
        "enabled": True,
        "source_url": "https://example.test/feed",
        "platform": "unknown-shop",
        "feed_format": "auto",
    }
    entry.update(overrides)
    return entry


def test_builds_enabled_generic_sources() -> None:
    registry = SourceRegistry.from_dict({
        "sources": [
            config_entry(),
            config_entry(source_key="disabled:feed", enabled=False),
        ]
    })

    adapters = registry.build_enabled()

    assert len(adapters) == 1
    assert isinstance(adapters[0], GenericAdapter)
    assert adapters[0].source_key == "unknown-shop:promotions"


def test_empty_config_is_valid() -> None:
    assert SourceRegistry.from_dict({"sources": []}).build_enabled() == ()


def test_rejects_duplicate_source_keys() -> None:
    with pytest.raises(ValueError, match="duplicate source_key"):
        SourceRegistry.from_dict({"sources": [config_entry(), config_entry()]})


@pytest.mark.parametrize("bad_url", ["http://example.test/feed", "/feed", ""])
def test_rejects_non_https_source_url(bad_url: str) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        SourceRegistry.from_dict({"sources": [config_entry(source_url=bad_url)]})


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        SourceRegistry.from_dict({"sources": [config_entry(mystery=True)]})


def test_rejects_unknown_adapter_instead_of_falling_back() -> None:
    registry = SourceRegistry.from_dict({
        "sources": [config_entry(adapter="unregistered-platform")]
    })

    with pytest.raises(ValueError, match="no adapter factory"):
        registry.build_enabled()


def test_custom_adapter_factory_is_extensible() -> None:
    class StubAdapter:
        source_key = "custom:source"

        def parse(self, payload: bytes | str) -> list[object]:
            return []

        def normalize(self, observations: list[object]) -> list[object]:
            return []

    registry = SourceRegistry([
        SourceDefinition(
            source_key="custom:source",
            adapter_type="custom",
            enabled=True,
            source_url="https://example.test/source",
        )
    ])
    registry.register_factory("custom", lambda definition: StubAdapter())

    assert registry.build_enabled()[0].source_key == "custom:source"


def test_loads_json_configuration(tmp_path) -> None:
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"sources": [config_entry()]}), encoding="utf-8")

    registry = SourceRegistry.load(path)

    assert len(registry.definitions) == 1
    assert registry.definitions[0].source_key == "unknown-shop:promotions"
