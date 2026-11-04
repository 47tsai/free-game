from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from free_game.adapters import GenericAdapter, GenericSourceConfig
from free_game.ingestion import IngestionPipeline


def make_adapter() -> GenericAdapter:
    return GenericAdapter(
        GenericSourceConfig(
            source_key="unknown-shop:feed",
            source_url="https://example.test/feed",
            platform="unknown-shop",
        )
    )


def test_pipeline_runs_generic_adapter_and_returns_observations_and_candidates() -> None:
    result = IngestionPipeline().run(
        make_adapter(),
        '<rss><channel><item><guid>g-1</guid><title>Free Game</title>'
        '<link>https://example.test/game/1</link></item></channel></rss>',
    )

    assert result.source_key == "unknown-shop:feed"
    assert len(result.observations) == 1
    assert len(result.candidates) == 1
    assert result.candidates[0].verification_status == "candidate"
    assert result.issues == ()


def test_pipeline_deduplicates_same_source_external_id() -> None:
    adapter = make_adapter()
    payload = '{"items":['         '{"id":"same","title":"First","url":"https://example.test/1"},'         '{"id":"same","title":"Duplicate","url":"https://example.test/2"}]}'

    result = IngestionPipeline().run(adapter, payload)

    assert len(result.candidates) == 1
    assert len(result.issues) == 1
    assert result.issues[0].reason == "duplicate_source_record"


def test_pipeline_rejects_timezone_naive_candidate() -> None:
    adapter = make_adapter()
    observation = adapter.parse(
        '<rss><channel><item><guid>g-1</guid><title>Free Game</title></item></channel></rss>'
    )[0]
    candidate = adapter.normalize([observation])[0]
    naive = replace(candidate, observed_at=datetime(2026, 11, 4))
    adapter.normalize = lambda _items: [naive]  # type: ignore[method-assign]

    result = IngestionPipeline().run(
        adapter,
        '<rss><channel><item><guid>g-1</guid><title>Free Game</title></item></channel></rss>',
    )

    assert result.candidates == ()
    assert result.issues[0].reason == "observed_at_must_be_timezone_aware"


def test_pipeline_rejects_adapter_verification_claim() -> None:
    adapter = make_adapter()
    observation = adapter.parse(
        '<rss><channel><item><guid>g-1</guid><title>Free Game</title></item></channel></rss>'
    )[0]
    candidate = adapter.normalize([observation])[0]
    adapter.normalize = lambda _items: [replace(candidate, verification_status="verified")]  # type: ignore[method-assign]

    result = IngestionPipeline().run(
        adapter,
        '<rss><channel><item><guid>g-1</guid><title>Free Game</title></item></channel></rss>',
    )

    assert result.candidates == ()
    assert result.issues[0].reason == "adapter_cannot_set_verification_status"


def test_pipeline_rejects_reversed_offer_window() -> None:
    adapter = make_adapter()
    observation = adapter.parse(
        '<rss><channel><item><guid>g-1</guid><title>Free Game</title></item></channel></rss>'
    )[0]
    candidate = adapter.normalize([observation])[0]
    adapter.normalize = lambda _items: [
        replace(
            candidate,
            offer_start_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
            offer_end_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        )
    ]  # type: ignore[method-assign]

    result = IngestionPipeline().run(
        adapter,
        '<rss><channel><item><guid>g-1</guid><title>Free Game</title></item></channel></rss>',
    )

    assert result.candidates == ()
    assert result.issues[0].reason == "offer_end_before_start"
