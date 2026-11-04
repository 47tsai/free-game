from __future__ import annotations

from datetime import timezone

import pytest

from free_game.adapters import GenericAdapter, GenericSourceConfig


def make_adapter(**overrides: object) -> GenericAdapter:
    values: dict[str, object] = {
        "source_key": "unknown-shop:promotions",
        "source_url": "https://example.test/feed",
        "platform": "unknown-shop",
    }
    values.update(overrides)
    return GenericAdapter(GenericSourceConfig(**values))  # type: ignore[arg-type]


def test_parses_rss_and_preserves_source_evidence() -> None:
    adapter = make_adapter()
    payload = """<?xml version="1.0"?>
    <rss version="2.0"><channel><item>
      <title>Example Free Game</title>
      <link>https://example.test/game/123</link>
      <guid>game-123</guid>
      <description>Free this weekend</description>
    </item></channel></rss>"""

    observations = adapter.parse(payload)

    assert len(observations) == 1
    item = observations[0]
    assert item.source_key == "unknown-shop:promotions"
    assert item.external_id == "game-123"
    assert item.raw_title == "Example Free Game"
    assert item.source_url == "https://example.test/game/123"
    assert "Free this weekend" in (item.raw_description or "")
    assert item.raw_data_excerpt
    assert item.observed_at.tzinfo == timezone.utc


def test_auto_detects_atom_feed() -> None:
    adapter = make_adapter()
    payload = """<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><id>tag:example.test,2026:1</id><title>Atom Game</title>
      <link href="https://example.test/game/1" /></entry>
    </feed>"""

    observations = adapter.parse(payload)

    assert len(observations) == 1
    assert observations[0].raw_title == "Atom Game"
    assert observations[0].source_url == "https://example.test/game/1"


def test_parses_json_feed() -> None:
    adapter = make_adapter(feed_format="json")
    payload = """{"version":"https://jsonfeed.org/version/1.1","items":[
      {"id":"abc","title":"JSON Game","url":"https://example.test/abc",
       "content_text":"A short description"}
    ]}"""

    observations = adapter.parse(payload)

    assert len(observations) == 1
    assert observations[0].external_id == "abc"
    assert observations[0].raw_title == "JSON Game"


def test_normalization_is_conservative_and_never_verifies() -> None:
    adapter = make_adapter()
    observations = adapter.parse(
        '<rss><channel><item><title>Unverified Game</title>'
        '<link>https://example.test/game</link></item></channel></rss>'
    )

    candidates = adapter.normalize(observations)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.platform == "unknown-shop"
    assert candidate.external_product_id is None
    assert candidate.verification_status == "candidate"
    assert candidate.title == "Unverified Game"


def test_missing_title_is_not_normalized() -> None:
    adapter = make_adapter()
    observations = adapter.parse('<rss><channel><item><link>https://example.test/1</link></item></channel></rss>')

    assert len(observations) == 1
    assert "missing_title" in observations[0].warnings
    assert adapter.normalize(observations) == []


def test_rejects_invalid_json() -> None:
    adapter = make_adapter(feed_format="json")

    with pytest.raises(ValueError, match="invalid JSON feed"):
        adapter.parse("{not-json")


def test_rejects_non_https_source_configuration() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        GenericSourceConfig(source_key="bad", source_url="http://example.test/feed")


def test_caps_raw_evidence_excerpt() -> None:
    adapter = make_adapter(max_excerpt_chars=12)
    observations = adapter.parse(
        '{"items":[{"id":"1","title":"A title","description":"A long description"}]}'
    )

    assert len(observations[0].raw_data_excerpt or "") <= 12
