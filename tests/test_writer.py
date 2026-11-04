from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from free_game.adapters.base import NormalizedCandidate
from free_game.semantic_validation import validate_dataset
from free_game.writer import (
    ContentsConflictError,
    GitHubJsonWriter,
    StoredCollection,
)


class MemoryStore:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.shas: dict[str, str] = {}
        self.writes: list[tuple[str, dict, str | None]] = []
        self.conflict_once = False
        self.counter = 0

    def read(self, path: str) -> StoredCollection:
        return StoredCollection(
            document=deepcopy(self.documents.get(path, {
                "schema_version": 1,
                "updated_at": "2026-11-04T00:00:00Z",
                "records": [],
            })),
            sha=self.shas.get(path),
        )

    def write(self, path: str, document: dict, sha: str | None) -> str:
        if self.conflict_once:
            self.conflict_once = False
            self.documents[path] = {
                "schema_version": 1,
                "updated_at": "2026-11-04T00:00:00Z",
                "records": [],
            }
            self.shas[path] = "concurrent-change"
            raise ContentsConflictError("conflict")
        current = self.shas.get(path)
        if current != sha:
            raise ContentsConflictError("stale sha")
        self.counter += 1
        next_sha = f"sha-{self.counter}"
        self.documents[path] = deepcopy(document)
        self.shas[path] = next_sha
        self.writes.append((path, deepcopy(document), sha))
        return next_sha


def candidate(**overrides) -> NormalizedCandidate:
    values = {
        "source_key": "steam:featured-categories",
        "platform": "steam",
        "external_product_id": "12345",
        "title": "Example Game",
        "product_url": "https://store.steampowered.com/app/12345/",
        "observed_at": datetime(2026, 11, 4, tzinfo=timezone.utc),
        "verification_status": "candidate",
        "source_external_id": "12345",
    }
    values.update(overrides)
    return NormalizedCandidate(**values)


def test_writer_creates_product_and_source_record() -> None:
    store = MemoryStore()

    result = GitHubJsonWriter(store).write_candidates([candidate()])

    assert result.products_created == 1
    assert result.source_records_created == 1
    assert len(result.commit_shas) == 2
    products = store.documents[GitHubJsonWriter.PRODUCTS_PATH]["records"]
    sources = store.documents[GitHubJsonWriter.SOURCE_RECORDS_PATH]["records"]
    assert len(products) == len(sources) == 1
    assert products[0]["game_id"] is None
    assert products[0]["external_product_id"] == "12345"
    assert products[0]["source_record_ids"] == [sources[0]["id"]]
    assert sources[0]["linked_entity_ids"] == [products[0]["id"]]
    validate_dataset({
        "games": store.documents[GitHubJsonWriter.GAMES_PATH],
        "products": store.documents[GitHubJsonWriter.PRODUCTS_PATH],
        "source_records": store.documents[GitHubJsonWriter.SOURCE_RECORDS_PATH],
    })


def test_repeated_run_is_idempotent() -> None:
    store = MemoryStore()
    writer = GitHubJsonWriter(store)

    first = writer.write_candidates([candidate()])
    second = writer.write_candidates([candidate()])

    assert first.products_created == 1
    assert second.products_created == 0
    assert second.products_updated == 1
    assert second.source_records_created == 0
    assert second.source_records_updated == 1
    assert len(store.documents[writer.PRODUCTS_PATH]["records"]) == 1
    assert len(store.documents[writer.SOURCE_RECORDS_PATH]["records"]) == 1


def test_same_product_from_multiple_sources_keeps_both_provenance_links() -> None:
    store = MemoryStore()
    writer = GitHubJsonWriter(store)

    writer.write_candidates([
        candidate(),
        candidate(
            source_key="steam:another-feed",
            source_external_id="feed-item-9",
            title="Example Game Updated",
        ),
    ])

    products = store.documents[writer.PRODUCTS_PATH]["records"]
    sources = store.documents[writer.SOURCE_RECORDS_PATH]["records"]
    assert len(products) == 1
    assert len(sources) == 2
    assert len(products[0]["source_record_ids"]) == 2


def test_candidate_without_product_identity_only_persists_discovery() -> None:
    store = MemoryStore()
    result = GitHubJsonWriter(store).write_candidates([
        candidate(platform=None, external_product_id=None, product_url="http://example.test/item")
    ])

    assert result.products_created == 0
    assert result.source_records_created == 1
    source = store.documents[GitHubJsonWriter.SOURCE_RECORDS_PATH]["records"][0]
    assert source["record_type"] == "discovery"
    assert source["url"] is None


def test_candidate_without_source_external_id_is_skipped() -> None:
    store = MemoryStore()
    result = GitHubJsonWriter(store).write_candidates([
        candidate(source_external_id=None)
    ])

    assert result.candidates_skipped == 1
    assert store.writes == []


def test_non_candidate_verification_state_is_skipped() -> None:
    store = MemoryStore()
    result = GitHubJsonWriter(store).write_candidates([
        candidate(verification_status="verified")
    ])

    assert result.candidates_skipped == 1
    assert store.writes == []


def test_retries_sha_conflict_after_rereading() -> None:
    store = MemoryStore()
    store.conflict_once = True

    result = GitHubJsonWriter(store).write_candidates([candidate()])

    assert result.products_created == 1
    assert result.source_records_created == 1
    assert len(store.writes) == 2


def test_rejects_exhausted_conflicts() -> None:
    class AlwaysConflict(MemoryStore):
        def write(self, path: str, document: dict, sha: str | None) -> str:
            raise ContentsConflictError("conflict")

    with pytest.raises(ContentsConflictError):
        GitHubJsonWriter(AlwaysConflict(), max_conflict_retries=0).write_candidates([
            candidate()
        ])


def test_invalid_non_https_product_url_is_skipped() -> None:
    store = MemoryStore()
    result = GitHubJsonWriter(store).write_candidates([
        candidate(product_url="http://store.steampowered.com/app/12345/")
    ])

    assert result.candidates_skipped == 1
    assert store.writes == []



def test_reconciliation_creates_one_provisional_game_per_product() -> None:
    store = MemoryStore()
    writer = GitHubJsonWriter(store)

    result = writer.write_candidates([
        candidate(),
        candidate(
            platform="epic",
            external_product_id="epic-123",
            source_key="epic:free-games",
            source_external_id="epic-123",
            product_url="https://store.epicgames.com/p/example",
        ),
    ])

    games = store.documents[writer.GAMES_PATH]["records"]
    products = store.documents[writer.PRODUCTS_PATH]["records"]
    assert result.games_created == 2
    assert result.products_linked_to_games == 2
    assert len(games) == 2
    assert len({product["game_id"] for product in products}) == 2
    assert all(game["normalized_title"] == "example game" for game in games)
    validate_dataset({
        "games": store.documents[writer.GAMES_PATH],
        "products": store.documents[writer.PRODUCTS_PATH],
        "source_records": store.documents[writer.SOURCE_RECORDS_PATH],
    })


def test_reconciliation_is_idempotent_and_does_not_merge_same_titles() -> None:
    store = MemoryStore()
    writer = GitHubJsonWriter(store)
    writer.write_candidates([
        candidate(),
        candidate(
            platform="epic",
            external_product_id="epic-123",
            source_key="epic:free-games",
            source_external_id="epic-123",
            product_url="https://store.epicgames.com/p/example",
        ),
    ])
    first_game_ids = {
        item["id"] for item in store.documents[writer.GAMES_PATH]["records"]
    }

    result = writer.reconcile_products_to_games()

    second_game_ids = {
        item["id"] for item in store.documents[writer.GAMES_PATH]["records"]
    }
    assert result[0] == (0, 0)
    assert result[3] == 0
    assert second_game_ids == first_game_ids
    assert len(second_game_ids) == 2


def test_discovery_only_source_record_does_not_create_game() -> None:
    store = MemoryStore()
    writer = GitHubJsonWriter(store)
    writer.write_candidates([
        candidate(platform=None, external_product_id=None, product_url=None)
    ])

    assert writer.GAMES_PATH not in store.documents
    assert writer.PRODUCTS_PATH not in store.documents
