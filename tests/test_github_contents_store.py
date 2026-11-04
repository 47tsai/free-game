from __future__ import annotations

import base64
import json

from free_game.writer import GitHubContentsStore


class FakeHTTPResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._body


def test_github_contents_store_reads_base64_json(monkeypatch) -> None:
    document = {
        "schema_version": 1,
        "updated_at": "2026-11-04T00:00:00Z",
        "records": [],
    }
    encoded = base64.b64encode(json.dumps(document).encode()).decode()
    response = FakeHTTPResponse(200, json.dumps({
        "content": encoded,
        "sha": "blob-sha",
    }).encode())

    monkeypatch.setattr("free_game.writer.urlopen", lambda request, timeout: response)
    stored = GitHubContentsStore("47tsai/free-game", "test-token").read(
        "data/catalog/products.json"
    )

    assert stored.document == document
    assert stored.sha == "blob-sha"


def test_github_contents_store_creates_missing_collection(monkeypatch) -> None:
    response = FakeHTTPResponse(404, b"{}")
    monkeypatch.setattr("free_game.writer.urlopen", lambda request, timeout: response)

    stored = GitHubContentsStore("47tsai/free-game", "test-token").read(
        "data/catalog/products.json"
    )

    assert stored.sha is None
    assert stored.document["schema_version"] == 1
    assert stored.document["records"] == []


def test_github_contents_store_writes_sha_and_branch(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data)
        return FakeHTTPResponse(200, json.dumps({
            "content": {"sha": "new-blob-sha"}
        }).encode())

    monkeypatch.setattr("free_game.writer.urlopen", fake_urlopen)
    store = GitHubContentsStore(
        "47tsai/free-game",
        "secret-token",
        branch="main",
    )
    document = {
        "schema_version": 1,
        "updated_at": "2026-11-04T00:00:00Z",
        "records": [],
    }

    sha = store.write("data/catalog/products.json", document, "old-blob-sha")

    assert sha == "new-blob-sha"
    assert captured["method"] == "PUT"
    assert captured["payload"]["sha"] == "old-blob-sha"
    assert captured["payload"]["branch"] == "main"
    decoded = base64.b64decode(captured["payload"]["content"]).decode()
    assert json.loads(decoded) == document
    assert any("secret-token" in value for value in captured["headers"].values())


def test_github_contents_store_does_not_expose_network_error_details(monkeypatch) -> None:
    from urllib.error import URLError

    def fail(request, timeout):
        raise URLError("secret-token must not leak")

    monkeypatch.setattr("free_game.writer.urlopen", fail)
    store = GitHubContentsStore("47tsai/free-game", "secret-token")

    try:
        store.read("data/catalog/products.json")
    except Exception as exc:
        assert "secret-token" not in str(exc)
        assert str(exc) == "github_contents_network_error"
    else:
        raise AssertionError("expected network failure")
