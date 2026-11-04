from __future__ import annotations

from copy import deepcopy

import pytest

from free_game.semantic_validation import SemanticValidationError, validate_dataset


NOW = "2026-11-04T00:00:00Z"


def collection(*records: dict) -> dict:
    return {"schema_version": 1, "updated_at": NOW, "records": list(records)}


def game() -> dict:
    return {
        "id": "game-1",
        "title": "Example Game",
        "normalized_title": "example game",
        "created_at": NOW,
        "updated_at": NOW,
    }


def product() -> dict:
    return {
        "id": "product-1",
        "game_id": "game-1",
        "platform": "steam",
        "external_product_id": "12345",
        "title": "Example Game",
        "product_url": "https://store.steampowered.com/app/12345",
        "created_at": NOW,
        "updated_at": NOW,
    }


def offer() -> dict:
    return {
        "id": "offer-1",
        "product_id": "product-1",
        "platform": "steam",
        "source_record_ids": [],
        "title": "Example Game",
        "starts_at": None,
        "ends_at": NOW,
        "deadline_status": "known",
        "status": "active",
        "verification_status": "verified",
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }


def claim() -> dict:
    return {
        "id": "claim-1",
        "user_id": "user-1",
        "product_id": "product-1",
        "status": "claimed",
        "source": "manual",
        "claimed_at": NOW,
        "updated_at": NOW,
    }


def notification() -> dict:
    return {
        "id": "notification-1",
        "offer_id": "offer-1",
        "notification_type": "new_offer",
        "channel": "discord",
        "idempotency_key": "new_offer:offer-1:discord",
        "status": "sent",
        "attempt_count": 1,
        "created_at": NOW,
        "sent_at": NOW,
    }


def valid_dataset() -> dict:
    return {
        "games": collection(game()),
        "products": collection(product()),
        "offers": collection(offer()),
        "claims": collection(claim()),
        "notifications": collection(notification()),
    }


def test_consistent_dataset_passes() -> None:
    validate_dataset(valid_dataset())


def test_missing_game_reference_is_rejected() -> None:
    data = valid_dataset()
    data["products"]["records"][0]["game_id"] = "missing-game"

    with pytest.raises(SemanticValidationError, match="missing game"):
        validate_dataset(data)


def test_missing_product_reference_is_rejected() -> None:
    data = valid_dataset()
    data["offers"]["records"][0]["product_id"] = "missing-product"

    with pytest.raises(SemanticValidationError, match="missing product"):
        validate_dataset(data)


def test_duplicate_claim_for_same_user_and_product_is_rejected() -> None:
    data = valid_dataset()
    duplicate = deepcopy(data["claims"]["records"][0])
    duplicate["id"] = "claim-2"
    data["claims"]["records"].append(duplicate)

    with pytest.raises(SemanticValidationError, match="duplicate user_id/product_id"):
        validate_dataset(data)


def test_duplicate_product_platform_identity_is_rejected() -> None:
    data = valid_dataset()
    duplicate = deepcopy(data["products"]["records"][0])
    duplicate["id"] = "product-2"
    data["products"]["records"].append(duplicate)

    with pytest.raises(SemanticValidationError, match="duplicate platform/external_product_id"):
        validate_dataset(data)


def test_duplicate_notification_idempotency_key_is_rejected() -> None:
    data = valid_dataset()
    duplicate = deepcopy(data["notifications"]["records"][0])
    duplicate["id"] = "notification-2"
    data["notifications"]["records"].append(duplicate)

    with pytest.raises(SemanticValidationError, match="duplicate idempotency_key"):
        validate_dataset(data)


def test_partial_dataset_checks_only_available_references() -> None:
    validate_dataset({"claims": collection(claim())})


def test_invalid_collection_schema_is_reported() -> None:
    with pytest.raises(SemanticValidationError, match="schema validation failed"):
        validate_dataset({"games": {"records": []}})


def test_unknown_collection_name_is_rejected() -> None:
    with pytest.raises(SemanticValidationError, match="Unknown collection name"):
        validate_dataset({"game": collection(game())})
