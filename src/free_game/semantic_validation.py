"""Cross-collection semantic validation for persisted Free Game datasets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from jsonschema import ValidationError

from free_game.validation import validate_collection

_COLLECTION_NAMES = (
    "games",
    "products",
    "offers",
    "claims",
    "claim_events",
    "notifications",
    "source_records",
)


class SemanticValidationError(ValueError):
    """Raised when datasets are individually valid but inconsistent together."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("\n".join(errors))


def _records(
    collections: Mapping[str, Mapping[str, Any]],
    name: str,
) -> list[dict[str, Any]]:
    document = collections.get(name)
    if not isinstance(document, Mapping):
        return []
    records = document.get("records")
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _duplicate_values(
    records: list[dict[str, Any]],
    key: Callable[[dict[str, Any]], Any],
) -> list[str]:
    seen: set[Any] = set()
    duplicates: list[str] = []
    for record in records:
        value = key(record)
        if value in seen:
            duplicates.append(str(value))
        else:
            seen.add(value)
    return duplicates


def validate_dataset(
    collections: Mapping[str, Mapping[str, Any]],
) -> None:
    """Validate supplied collections and their cross-file references.

    Collection keys are filename stems such as games or claim_events.
    Missing collections are treated as unavailable, so callers can validate a
    partial dataset. Present collections must pass the canonical JSON Schema.
    Raises SemanticValidationError with all detected problems.
    """
    errors: list[str] = []
    unknown_names = sorted(set(collections) - set(_COLLECTION_NAMES))
    errors.extend(f"Unknown collection name: {name}" for name in unknown_names)

    valid_names: set[str] = set()
    for name in _COLLECTION_NAMES:
        if name not in collections:
            continue
        try:
            validate_collection(dict(collections[name]))
        except (ValidationError, TypeError, ValueError) as exc:
            errors.append(f"{name}: schema validation failed: {exc}")
        else:
            valid_names.add(name)

    records = {
        name: _records(collections, name) if name in valid_names else []
        for name in _COLLECTION_NAMES
    }

    for name, items in records.items():
        for duplicate in _duplicate_values(items, lambda item: item["id"]):
            errors.append(f"{name}: duplicate id {duplicate!r}")

    games_by_id = {item["id"] for item in records["games"]}
    products_by_id = {item["id"] for item in records["products"]}
    offers_by_id = {item["id"] for item in records["offers"]}

    for product in records["products"]:
        game_id = product["game_id"]
        if game_id is not None and "games" in valid_names and game_id not in games_by_id:
            errors.append(
                f"products: product {product['id']!r} references missing game {game_id!r}"
            )

    for offer in records["offers"]:
        product_id = offer["product_id"]
        if "products" in valid_names and product_id not in products_by_id:
            errors.append(
                f"offers: offer {offer['id']!r} references missing product {product_id!r}"
            )

    for claim in records["claims"]:
        product_id = claim["product_id"]
        if "products" in valid_names and product_id not in products_by_id:
            errors.append(
                f"claims: claim {claim['id']!r} references missing product {product_id!r}"
            )

    for event in records["claim_events"]:
        product_id = event["product_id"]
        if "products" in valid_names and product_id not in products_by_id:
            errors.append(
                f"claim_events: event {event['id']!r} references missing product {product_id!r}"
            )
        offer_id = event.get("offer_id")
        if offer_id is not None and "offers" in valid_names and offer_id not in offers_by_id:
            errors.append(
                f"claim_events: event {event['id']!r} references missing offer {offer_id!r}"
            )

    for notification in records["notifications"]:
        offer_id = notification["offer_id"]
        if "offers" in valid_names and offer_id not in offers_by_id:
            errors.append(
                f"notifications: notification {notification['id']!r} "
                f"references missing offer {offer_id!r}"
            )

    for duplicate in _duplicate_values(
        records["products"],
        lambda item: (item["platform"], item["external_product_id"]),
    ):
        errors.append(f"products: duplicate platform/external_product_id {duplicate!r}")

    for duplicate in _duplicate_values(
        records["claims"],
        lambda item: (item["user_id"], item["product_id"]),
    ):
        errors.append(f"claims: duplicate user_id/product_id {duplicate!r}")

    for duplicate in _duplicate_values(
        records["notifications"],
        lambda item: item["idempotency_key"],
    ):
        errors.append(f"notifications: duplicate idempotency_key {duplicate!r}")

    for duplicate in _duplicate_values(
        records["source_records"],
        lambda item: (item["source"], item["external_id"]),
    ):
        errors.append(f"source_records: duplicate source/external_id {duplicate!r}")

    if errors:
        raise SemanticValidationError(errors)
