from __future__ import annotations

import pytest

from free_game.runner import HTTPFetchResponse, HTTPFetcher, SourceFetchError


class FakeResponse:
    status = 200
    def __init__(self, body, final_url):
        self.body = body
        self.final_url = final_url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.final_url
    def read(self, limit): return self.body[:limit]


def test_fetcher_returns_body_and_final_url(monkeypatch):
    monkeypatch.setattr("free_game.runner.urlopen", lambda request, timeout: FakeResponse(b"rss", request.full_url))
    result = HTTPFetcher().fetch("https://example.test/feed")
    assert isinstance(result, HTTPFetchResponse)
    assert result.body == b"rss"
    assert result.final_url == "https://example.test/feed"


def test_fetcher_rejects_non_https_urls():
    with pytest.raises(SourceFetchError, match="source_url_must_be_absolute_https"):
        HTTPFetcher().fetch("http://example.test/feed")


def test_fetcher_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr("free_game.runner.urlopen", lambda request, timeout: FakeResponse(b"12345", request.full_url))
    with pytest.raises(SourceFetchError, match="response_too_large"):
        HTTPFetcher(max_response_bytes=4).fetch("https://example.test/feed")


def test_fetcher_rejects_non_https_redirect(monkeypatch):
    monkeypatch.setattr("free_game.runner.urlopen", lambda request, timeout: FakeResponse(b"rss", "http://example.test/feed"))
    with pytest.raises(SourceFetchError, match="redirected_to_non_https_url"):
        HTTPFetcher().fetch("https://example.test/feed")
