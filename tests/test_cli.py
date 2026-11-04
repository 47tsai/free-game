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
