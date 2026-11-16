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
    candidates, failures, skipped = collect_candidates(RSS, fetcher=FakeFetcher())
    assert failures == []
    assert skipped == []
    assert len(candidates) == 1
    assert candidates[0].platform == "steam"
    assert candidates[0].external_product_id == "785890"
    assert candidates[0].title == "Hexologic"
    assert candidates[0].article_url.endswith("/123")
    assert candidates[0].image_url == "https://example.com/cover.jpg"


def test_collect_candidates_skips_article_without_any_storefront_signal():
    # An RSS-matched article with no storefront-domain URL in any parsed
    # href/src attribute (e.g. a Twitch Drops serial-code giveaway) is a
    # non-offer news item, not an extraction failure: it is skipped and the
    # run must not fail because of it.
    class FakeFetcher:
        def fetch(self, url):
            body = b"<html><body>No storefront link</body></html>"
            return HTTPFetchResponse(body, 200, url)
    candidates, failures, skipped = collect_candidates(RSS, fetcher=FakeFetcher())
    assert candidates == []
    assert failures == []
    assert skipped == [{
        "article_id": "article-123",
        "error": "no_storefront_signal",
        "html_bytes": len(b"<html><body>No storefront link</body></html>"),
        "external_links_found": 0,
        "storefront_links_found": 0,
        "storefront_url_attributes_seen": 0,
        "raw_storefront_domain_mentions": 0,
        "href_attributes_found": 0,
        "body_tag_present": True,
        "anchor_tags_seen": 0,
        "anchor_tags_with_href": 0,
        "anchor_tags_skipped_by_context": 0,
        "max_skip_depth": 0,
        "active_skip_tags": "",
        "skipped_anchor_contexts": "",
    }]


def test_collect_candidates_reports_article_when_store_signal_exists_but_extraction_fails():
    # A storefront anchor whose title cannot be resolved is still a real
    # extraction failure: the article does carry a storefront signal.
    rss = """<rss><channel><item><title>限時免費</title><link>https://www.4gamers.com.tw/news/detail/123</link><guid>article-123</guid><description>限免</description></item></channel></rss>""".encode("utf-8")
    class FakeFetcher:
        def fetch(self, url):
            body = b'<html><body><a href="https://store.steampowered.com/app/785890/Hexologic/">\xe7\xab\x8b\xe5\x8d\xb3\xe9\xa0\x98\xe5\x8f\x96</a></body></html>'
            return HTTPFetchResponse(body, 200, url)
    candidates, failures, skipped = collect_candidates(rss, fetcher=FakeFetcher())
    assert candidates == []
    assert skipped == []
    assert failures == [{
        "article_id": "article-123",
        "error": "no_storefront_products_extracted",
        "html_bytes": len(b'<html><body><a href="https://store.steampowered.com/app/785890/Hexologic/">\xe7\xab\x8b\xe5\x8d\xb3\xe9\xa0\x98\xe5\x8f\x96</a></body></html>'),
        "external_links_found": 1,
        "storefront_links_found": 1,
        "storefront_url_attributes_seen": 1,
        "raw_storefront_domain_mentions": 1,
        "href_attributes_found": 1,
        "body_tag_present": True,
        "anchor_tags_seen": 1,
        "anchor_tags_with_href": 1,
        "anchor_tags_skipped_by_context": 0,
        "max_skip_depth": 0,
        "active_skip_tags": "",
        "skipped_anchor_contexts": "",
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
    monkeypatch.setattr("free_game.cli.collect_candidates", lambda payload: ([candidate], [], []))
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


def test_ingest_command_succeeds_when_only_non_offer_article_is_skipped(monkeypatch, capsys):
    def fake_fetch(self, url):
        if url == "https://www.4gamers.com.tw/rss/latest-news":
            return HTTPFetchResponse(RSS, 200, url)
        return HTTPFetchResponse(b"<html><body>No storefront link</body></html>", 200, url)
    monkeypatch.setattr("free_game.cli._make_writer", lambda: object())
    monkeypatch.setattr("free_game.cli.HTTPFetcher.fetch", fake_fetch)
    assert main(["ingest"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "success"
    assert output["candidates"] == 0
    assert output["failed_articles"] == []
    assert len(output["skipped_articles"]) == 1
    assert output["skipped_articles"][0]["error"] == "no_storefront_signal"
    assert output["write"] is None


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
