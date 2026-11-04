from __future__ import annotations

from free_game.registry import SourceRegistry
from free_game.runner import HTTPFetchResponse, SourceRunner


class FakeFetcher:
    def __init__(self, responses: dict[str, bytes | Exception]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    def fetch(self, url: str) -> HTTPFetchResponse:
        self.requested.append(url)
        result = self.responses[url]
        if isinstance(result, Exception):
            raise result
        return HTTPFetchResponse(body=result, status_code=200, final_url=url)


def test_runner_fetches_and_ingests_enabled_sources() -> None:
    url = "https://example.test/feed"
    registry = SourceRegistry.from_dict({
        "sources": [{
            "source_key": "example:feed",
            "adapter": "generic",
            "enabled": True,
            "source_url": url,
            "platform": "example",
        }]
    })
    fetcher = FakeFetcher({
        url: b'<rss><channel><item><guid>g1</guid><title>Free Game</title>'
        b'<link>https://example.test/game</link></item></channel></rss>'
    })

    results = SourceRunner(registry, fetcher=fetcher).run_all()

    assert len(results) == 1
    result = results[0]
    assert result.succeeded
    assert result.fetch_result is not None
    assert result.fetch_result.http_status == 200
    assert len(result.fetch_result.payload_hash or "") == 64
    assert result.ingestion_result is not None
    assert result.ingestion_result.candidates[0].title == "Free Game"
    assert fetcher.requested == [url]


def test_one_source_failure_does_not_stop_other_sources() -> None:
    failed_url = "https://example.test/broken"
    good_url = "https://example.test/good"
    registry = SourceRegistry.from_dict({
        "sources": [
            {
                "source_key": "example:broken",
                "adapter": "generic",
                "enabled": True,
                "source_url": failed_url,
            },
            {
                "source_key": "example:good",
                "adapter": "generic",
                "enabled": True,
                "source_url": good_url,
            },
        ]
    })
    fetcher = FakeFetcher({
        failed_url: ValueError("upstream failure"),
        good_url: b'<rss><channel><item><title>Still Works</title></item></channel></rss>',
    })

    results = SourceRunner(registry, fetcher=fetcher).run_all()

    assert [result.source_key for result in results] == ["example:broken", "example:good"]
    assert results[0].succeeded is False
    assert results[0].error == "ValueError:source_processing_failed"
    assert results[1].succeeded is True


def test_runner_records_parser_failure_after_fetch() -> None:
    url = "https://example.test/not-json"
    registry = SourceRegistry.from_dict({
        "sources": [{
            "source_key": "example:feed",
            "adapter": "generic",
            "enabled": True,
            "source_url": url,
            "feed_format": "json",
        }]
    })

    result = SourceRunner(
        registry,
        fetcher=FakeFetcher({url: b"{broken"}),
    ).run_all()[0]

    assert result.fetch_result is not None
    assert result.ingestion_result is None
    assert result.error == "ValueError:source_processing_failed"


def test_runner_redacts_sensitive_query_parameters() -> None:
    redacted = SourceRunner._redact_url(
        "https://example.test/feed?region=tw&api_key=secret&signature=abc"
    )

    assert "region=tw" in redacted
    assert "api_key=%5BREDACTED%5D" in redacted
    assert "signature=%5BREDACTED%5D" in redacted
    assert "secret" not in redacted
    assert "abc" not in redacted


def test_runner_skips_disabled_sources() -> None:
    url = "https://example.test/disabled"
    registry = SourceRegistry.from_dict({
        "sources": [{
            "source_key": "example:disabled",
            "adapter": "generic",
            "enabled": False,
            "source_url": url,
        }]
    })
    fetcher = FakeFetcher({})

    assert SourceRunner(registry, fetcher=fetcher).run_all() == ()
    assert fetcher.requested == []
