from __future__ import annotations

import json
from datetime import datetime, timezone

from free_game.adapters.base import NormalizedCandidate
from free_game.cli import collect_candidates, main
from free_game.runner import HTTPFetchResponse


RSS = """<rss><channel><item><title>限時免費《Hexologic》</title><link>https://www.4gamers.com.tw/news/detail/123</link><guid>article-123</guid><description>限免</description></item></channel></rss>""".encode("utf-8")


def test_collect_candidates_extracts_storefront_product(monkeypatch):
    class FakeFetcher:
        def fetch(self, url):
            assert url == "https://www.4gamers.com.tw/news/detail/123"
            return HTTPFetchResponse(b'<html><head><meta property="og:image" content="https://example.com/cover.jpg"></head><body><a href="https://store.steampowered.com/app/785890/Hexologic/">Hexologic</a></body></html>', 200, url)
    candidates, failures = collect_candidates(RSS, fetcher=FakeFetcher())
    assert failures == []
    assert len(candidates) == 1
    assert candidates[0].platform == "steam"
    assert candidates[0].external_product_id == "785890"
    assert candidates[0].title == "Hexologic"
    assert candidates[0].article_url.endswith("/123")
    assert candidates[0].image_url == "https://example.com/cover.jpg"


def test_collect_candidates_reports_article_when_store_link_is_missing():
    class FakeFetcher:
        def fetch(self, url):
            body = b"<html><body>No storefront link</body></html>"
            return HTTPFetchResponse(body, 200, url)
    candidates, failures = collect_candidates(RSS, fetcher=FakeFetcher())
    assert candidates == []
    assert failures == [{
        "article_id": "article-123",
        "error": "no_storefront_products_extracted",
        "html_bytes": len(b"<html><body>No storefront link</body></html>"),
        "external_links_found": 0,
        "storefront_links_found": 0,
        "raw_storefront_domain_mentions": 0,
        "href_attributes_found": 0,
        "body_tag_present": True,
    }]


def test_ingest_command_writes_game_records_and_notifies(monkeypatch, capsys):
    candidate = NormalizedCandidate(
        source_key="4gamers:latest-news", platform="steam", external_product_id="785890",
        title="Hexologic", product_url="https://store.steampowered.com/app/785890/Hexologic/",
        observed_at=datetime(2026, 11, 4, tzinfo=timezone.utc), source_external_id="article-123",
        article_url="https://www.4gamers.com.tw/news/detail/123",
    )
    monkeypatch.setattr("free_game.cli._make_writer", lambda: object())
    monkeypatch.setattr("free_game.cli.HTTPFetcher.fetch", lambda self, url: HTTPFetchResponse(RSS, 200, url))
    monkeypatch.setattr("free_game.cli.collect_candidates", lambda payload: ([candidate], []))
    monkeypatch.setattr("free_game.cli.GitHubJsonWriter", lambda store: None)
    class FakeWriter:
        def write_candidates(self, candidates):
            assert candidates == [candidate]
            return type("Result", (), {"games_created": 1, "games_updated": 0, "candidates_skipped": 0})()
    writer = FakeWriter()
    monkeypatch.setattr("free_game.cli._make_writer", lambda: writer)
    monkeypatch.setattr("free_game.cli._send_notifications", lambda writer: {"status": "success", "sent": 1, "skipped": 0, "failed": 0})
    assert main(["ingest"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "success"
    assert output["write"]["games_created"] == 1


def test_fgc_sync_updates_claims_and_notifies(monkeypatch, capsys):
    class FakeWriter:
        def sync_fgc_claims(self, claims):
            assert claims == [{"title": "Hexologic"}]
            return (1, 0), "sha"
    monkeypatch.setattr("free_game.cli._make_writer", lambda: FakeWriter())
    monkeypatch.setattr("free_game.cli.fetch_fgc_claims", lambda: [{"title": "Hexologic"}])
    monkeypatch.setattr("free_game.cli._send_notifications", lambda writer: {"status": "success", "sent": 0, "skipped": 0, "failed": 0})
    assert main(["fgc-sync"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["fgc_claims"] == 1
