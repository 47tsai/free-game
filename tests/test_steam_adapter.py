from __future__ import annotations

import json
from datetime import timezone

import pytest

from free_game.adapters import SteamAdapter
from free_game.ingestion import IngestionPipeline


def make_adapter() -> SteamAdapter:
    return SteamAdapter()


def payload(items: list[dict[str, object]]) -> str:
    return json.dumps({"status": 1, "specials": {"items": items}})


def free_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": 123456,
        "type": 0,
        "name": "Example Game",
        "discounted": True,
        "discount_percent": 100,
        "original_price": 1999,
        "final_price": 0,
    }
    item.update(overrides)
    return item


def test_parses_zero_price_100_percent_discount_game() -> None:
    adapter = make_adapter()

    observations = adapter.parse(payload([free_item()]))

    assert len(observations) == 1
    observation = observations[0]
    assert observation.source_key == "steam:featured-categories"
    assert observation.external_id == "123456"
    assert observation.raw_title == "Example Game"
    assert observation.source_url == "https://store.steampowered.com/app/123456/"
    assert observation.observed_at.tzinfo == timezone.utc
    assert "requires_storefront_verification" in observation.warnings[0]


def test_normalizes_candidate_without_marking_verified() -> None:
    adapter = make_adapter()
    result = IngestionPipeline().run(adapter, payload([free_item()]))

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.platform == "steam"
    assert candidate.external_product_id == "123456"
    assert candidate.verification_status == "candidate"
    assert candidate.product_url == "https://store.steampowered.com/app/123456/"


@pytest.mark.parametrize(
    "item",
    [
        free_item(discounted=False),
        free_item(discount_percent=90),
        free_item(final_price=1),
        free_item(original_price=0),
        free_item(type=1),
        free_item(id=0),
        free_item(name=""),
    ],
)
def test_ignores_non_qualifying_items(item: dict[str, object]) -> None:
    assert make_adapter().parse(payload([item])) == []


def test_ignores_non_object_items() -> None:
    assert make_adapter().parse(payload(["not-an-item", None])) == []


def test_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="invalid Steam"):
        make_adapter().parse("{broken")


def test_rejects_missing_specials_bucket() -> None:
    with pytest.raises(ValueError, match="specials bucket"):
        make_adapter().parse(json.dumps({"status": 1}))


def test_rejects_failed_response_status() -> None:
    with pytest.raises(ValueError, match="status"):
        make_adapter().parse(json.dumps({"status": 0, "specials": {"items": []}}))


def test_rejects_non_steam_source_url() -> None:
    with pytest.raises(ValueError, match="store.steampowered.com"):
        SteamAdapter(source_url="https://example.test/feed")
