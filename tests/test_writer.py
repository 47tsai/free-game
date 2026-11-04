from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from free_game.adapters.base import NormalizedCandidate
from free_game.writer import ContentsConflictError, GitHubJsonWriter, StoredCollection


class MemoryStore:
    def __init__(self):
        self.documents = {}
        self.shas = {}
        self.writes = []
        self.conflict_once = False
        self.counter = 0

    def read(self, path):
        return StoredCollection(deepcopy(self.documents.get(path, {"schema_version": 1, "updated_at": "2026-11-04T00:00:00Z", "records": []})), self.shas.get(path))

    def write(self, path, document, sha):
        if self.conflict_once:
            self.conflict_once = False
            self.documents[path] = {"schema_version": 1, "updated_at": "2026-11-04T00:00:00Z", "records": []}
            self.shas[path] = "concurrent"
            raise ContentsConflictError("conflict")
        if self.shas.get(path) != sha:
            raise ContentsConflictError("stale sha")
        self.counter += 1
        next_sha = f"sha-{self.counter}"
        self.documents[path] = deepcopy(document)
        self.shas[path] = next_sha
        self.writes.append((path, deepcopy(document), sha))
        return next_sha


def candidate(**overrides):
    values = {
        "source_key": "4gamers:latest-news",
        "platform": "steam",
        "external_product_id": "785890",
        "title": "Hexologic",
        "product_url": "https://store.steampowered.com/app/785890/Hexologic/",
        "observed_at": datetime(2026, 11, 4, tzinfo=timezone.utc),
        "source_external_id": "4gamers-hexologic",
        "article_url": "https://www.4gamers.com.tw/news/detail/hexologic",
        "image_url": "https://example.com/hexologic.jpg",
    }
    values.update(overrides)
    return NormalizedCandidate(**values)


def test_writer_creates_one_complete_game_record():
    store = MemoryStore()
    result = GitHubJsonWriter(store).write_candidates([candidate()])
    assert result.games_created == 1
    assert result.games_updated == 0
    games = store.documents[GitHubJsonWriter.GAMES_PATH]["records"]
    assert len(games) == 1
    game = games[0]
    assert game["title"] == "Hexologic"
    assert game["platform"] == "steam"
    assert game["store_url"].endswith("/785890/Hexologic/")
    assert game["article_url"].endswith("/hexologic")
    assert game["cover_image_url"] == "https://example.com/hexologic.jpg"
    assert game["claim_status"] == "unclaimed"
    assert game["added_at"] == game["created_at"]


def test_repeated_ingestion_is_idempotent():
    store = MemoryStore()
    writer = GitHubJsonWriter(store)
    first = writer.write_candidates([candidate()])
    second = writer.write_candidates([candidate()])
    assert first.games_created == 1
    assert second.games_created == second.games_updated == 0
    assert len(store.documents[writer.GAMES_PATH]["records"]) == 1


def test_same_store_product_from_multiple_articles_stays_one_game():
    store = MemoryStore()
    writer = GitHubJsonWriter(store)
    writer.write_candidates([candidate(), candidate(source_external_id="second-article", article_url="https://www.4gamers.com.tw/news/detail/second")])
    games = store.documents[writer.GAMES_PATH]["records"]
    assert len(games) == 1
    assert games[0]["added_at"] == games[0]["created_at"]


def test_discovery_without_store_link_is_still_saved():
    store = MemoryStore()
    result = GitHubJsonWriter(store).write_candidates([candidate(platform=None, external_product_id=None, product_url="https://www.4gamers.com.tw/news/detail/discovery", article_url=None, image_url=None)])
    assert result.games_created == 1
    game = store.documents[GitHubJsonWriter.GAMES_PATH]["records"][0]
    assert game["platform"] is None
    assert game["store_url"] is None
    assert game["article_url"].endswith("/discovery")


def test_candidate_without_source_identity_is_skipped():
    store = MemoryStore()
    result = GitHubJsonWriter(store).write_candidates([candidate(source_external_id=None)])
    assert result.candidates_skipped == 1
    assert store.writes == []


def test_invalid_store_url_is_skipped():
    store = MemoryStore()
    result = GitHubJsonWriter(store).write_candidates([candidate(product_url="http://store.steampowered.com/app/785890/")])
    assert result.candidates_skipped == 1
    assert store.writes == []


def test_fgc_claim_is_saved_and_matched_to_later_4gamers_game():
    store = MemoryStore()
    writer = GitHubJsonWriter(store)
    writer.sync_fgc_claims([{"platform": "steam", "external_product_id": "785890", "title": "Hexologic", "store_url": "https://store.steampowered.com/app/785890/Hexologic/"}])
    placeholder = store.documents[writer.GAMES_PATH]["records"][0]
    assert placeholder["claim_status"] == "claimed"
    assert placeholder["claim_source"] == "fgc"
    writer.write_candidates([candidate()])
    games = store.documents[writer.GAMES_PATH]["records"]
    assert len(games) == 1
    assert games[0]["claim_status"] == "claimed"
    assert games[0]["article_url"].endswith("/hexologic")
    assert games[0]["cover_image_url"] == "https://example.com/hexologic.jpg"


def test_manual_claim_state_is_not_overwritten_by_fgc_sync():
    store = MemoryStore()
    writer = GitHubJsonWriter(store)
    writer.write_candidates([candidate()])
    game = store.documents[writer.GAMES_PATH]["records"][0]
    writer.update_game(game["id"], {"claim_status": "claimed", "claimed_at": "2026-11-04T01:00:00Z", "claim_source": "manual", "claim_notification_pending": True})
    writer.sync_fgc_claims([{"platform": "steam", "external_product_id": "785890", "title": "Hexologic", "store_url": candidate().product_url}])
    game = store.documents[writer.GAMES_PATH]["records"][0]
    assert game["claim_source"] == "manual"
    assert game["claim_notification_pending"] is True


def test_retries_sha_conflict_after_rereading():
    store = MemoryStore()
    store.conflict_once = True
    result = GitHubJsonWriter(store).write_candidates([candidate()])
    assert result.games_created == 1
    assert len(store.writes) == 1


def test_rejects_exhausted_sha_conflicts():
    class AlwaysConflict(MemoryStore):
        def write(self, path, document, sha):
            raise ContentsConflictError("conflict")
    with pytest.raises(ContentsConflictError):
        GitHubJsonWriter(AlwaysConflict(), max_conflict_retries=0).write_candidates([candidate()])
