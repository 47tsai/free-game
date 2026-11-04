from __future__ import annotations

import json
from datetime import datetime, timezone

from free_game.adapters.base import NormalizedCandidate
from free_game.ingestion import IngestionResult
from free_game.runner import SourceRunResult
from free_game.cli import main


def write_config(path, sources):
    path.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    return str(path)


def test_cli_returns_cleanly_when_no_sources_enabled(tmp_path, capsys) -> None:
    config = write_config(tmp_path / "sources.json", [])

    exit_code = main(["ingest", "--config", config])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "no_enabled_sources"


def test_cli_requires_token_only_when_candidates_need_persisting(
    tmp_path, monkeypatch, capsys
) -> None:
    config = write_config(tmp_path / "sources.json", [{
        "source_key": "example:feed",
        "adapter": "generic",
        "enabled": True,
        "source_url": "https://example.test/feed",
    }])
    candidate = NormalizedCandidate(
        source_key="example:feed",
        platform="example",
        external_product_id="42",
        title="Example",
        product_url="https://example.test/42",
        observed_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        source_external_id="feed-item-42",
    )
    result = SourceRunResult(
        source_key="example:feed",
        fetch_result=None,
        ingestion_result=IngestionResult(
            source_key="example:feed",
            observations=(),
            candidates=(candidate,),
            issues=(),
        ),
    )
    monkeypatch.setattr("free_game.cli.SourceRunner", lambda registry: type(
        "Runner", (), {"run_all": lambda self: (result,)}
    )())
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    exit_code = main(["ingest", "--config", config])

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_cli_persists_candidates_and_reports_summary(
    tmp_path, monkeypatch, capsys
) -> None:
    config = write_config(tmp_path / "sources.json", [{
        "source_key": "example:feed",
        "adapter": "generic",
        "enabled": True,
        "source_url": "https://example.test/feed",
    }])
    candidate = NormalizedCandidate(
        source_key="example:feed",
        platform="example",
        external_product_id="42",
        title="Example",
        product_url="https://example.test/42",
        observed_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        source_external_id="feed-item-42",
    )
    result = SourceRunResult(
        source_key="example:feed",
        fetch_result=None,
        ingestion_result=IngestionResult(
            source_key="example:feed",
            observations=(),
            candidates=(candidate,),
            issues=(),
        ),
    )
    monkeypatch.setattr("free_game.cli.SourceRunner", lambda registry: type(
        "Runner", (), {"run_all": lambda self: (result,)}
    )())
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    class FakeWriter:
        def __init__(self, store):
            pass

        def write_candidates(self, candidates):
            assert tuple(candidates) == (candidate,)
            return type("WriteResult", (), {
                "products_created": 1,
                "products_updated": 0,
                "games_created": 1,
                "products_linked_to_games": 1,
                "source_records_created": 1,
                "source_records_updated": 0,
                "candidates_skipped": 0,
            })()

    monkeypatch.setattr("free_game.cli.GitHubJsonWriter", FakeWriter)
    monkeypatch.setattr("free_game.cli.GitHubContentsStore", lambda *args, **kwargs: object())

    exit_code = main(["ingest", "--config", config])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "success"
    assert output["write"]["products_created"] == 1
    assert output["write"]["games_created"] == 1


def test_cli_expands_4gamers_articles_into_store_products(monkeypatch) -> None:
    from free_game.adapters.base import SourceObservation

    observation = SourceObservation(
        source_key="4gamers:latest-news",
        external_id="article-123",
        observed_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        source_url="https://www.4gamers.com.tw/news/detail/123",
        raw_title="限時免費《Example Game》",
        raw_description="本週限免",
    )
    fallback = NormalizedCandidate(
        source_key="4gamers:latest-news",
        platform=None,
        external_product_id=None,
        title=observation.raw_title,
        product_url=observation.source_url,
        observed_at=observation.observed_at,
        source_external_id=observation.external_id,
    )
    result = SourceRunResult(
        source_key="4gamers:latest-news",
        fetch_result=None,
        ingestion_result=IngestionResult(
            source_key="4gamers:latest-news",
            observations=(observation,),
            candidates=(fallback,),
            issues=(),
        ),
    )

    class FakeFetcher:
        def fetch(self, url):
            assert url == observation.source_url
            return type("Response", (), {
                "body": b'<html><body><a href="https://store.steampowered.com/app/12345/example/">Example Game</a></body></html>'
            })()

    monkeypatch.setattr("free_game.cli.HTTPFetcher", FakeFetcher)
    from free_game.cli import collect_candidates

    candidates, failures = collect_candidates((result,))

    assert failures == []
    assert len(candidates) == 1
    assert candidates[0].platform == "steam"
    assert candidates[0].external_product_id == "12345"
    assert candidates[0].title == "Example Game"


def test_cli_keeps_discovery_record_when_article_has_no_store_link(monkeypatch) -> None:
    from free_game.adapters.base import SourceObservation

    observation = SourceObservation(
        source_key="4gamers:latest-news",
        external_id="article-123",
        observed_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        source_url="https://www.4gamers.com.tw/news/detail/123",
        raw_title="限時免費情報",
    )
    fallback = NormalizedCandidate(
        source_key="4gamers:latest-news",
        platform=None,
        external_product_id=None,
        title=observation.raw_title,
        product_url=observation.source_url,
        observed_at=observation.observed_at,
        source_external_id=observation.external_id,
    )
    result = SourceRunResult(
        source_key="4gamers:latest-news",
        fetch_result=None,
        ingestion_result=IngestionResult(
            source_key="4gamers:latest-news",
            observations=(observation,),
            candidates=(fallback,),
            issues=(),
        ),
    )

    class FakeFetcher:
        def fetch(self, url):
            return type("Response", (), {"body": b"<html><body>No store links</body></html>"})()

    monkeypatch.setattr("free_game.cli.HTTPFetcher", FakeFetcher)
    from free_game.cli import collect_candidates

    candidates, failures = collect_candidates((result,))

    assert failures == []
    assert candidates == [fallback]
