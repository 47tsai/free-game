from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from free_game.validation import SCHEMA_PATH, load_schema, validate_collection, validate_file

ROOT = Path(__file__).resolve().parents[1]
VALID_FIXTURES = ROOT / "tests" / "fixtures" / "valid"


def test_canonical_schema_is_valid() -> None:
    schema = load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("fixture_name", ["games.json", "offers.json", "claims.json"])
def test_valid_fixtures_pass(fixture_name: str) -> None:
    validate_file(VALID_FIXTURES / fixture_name)


def test_empty_collection_is_valid() -> None:
    validate_collection(
        {
            "schema_version": 1,
            "updated_at": "2026-11-04T00:00:00Z",
            "records": [],
        }
    )


def test_offer_with_known_deadline_requires_ends_at() -> None:
    document = json.loads((VALID_FIXTURES / "offers.json").read_text(encoding="utf-8"))
    document["records"][0]["ends_at"] = None

    with pytest.raises(ValidationError):
        validate_collection(document)


def test_offer_with_unknown_deadline_may_omit_ends_at() -> None:
    document = json.loads((VALID_FIXTURES / "offers.json").read_text(encoding="utf-8"))
    offer = document["records"][0]
    offer["deadline_status"] = "unknown"
    offer["ends_at"] = None

    validate_collection(document)


def test_invalid_timestamp_is_rejected() -> None:
    document = json.loads((VALID_FIXTURES / "games.json").read_text(encoding="utf-8"))
    document["updated_at"] = "not-a-timestamp"

    with pytest.raises(ValidationError):
        validate_collection(document)


def test_unexpected_entity_field_is_rejected() -> None:
    document = json.loads((VALID_FIXTURES / "games.json").read_text(encoding="utf-8"))
    document["records"][0]["unexpected"] = True

    with pytest.raises(ValidationError):
        validate_collection(document)


def test_validator_uses_repository_schema_path() -> None:
    assert SCHEMA_PATH.is_file()
