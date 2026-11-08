from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from free_game.validation import SCHEMA_PATH, load_schema, validate_collection, validate_file

ROOT = Path(__file__).resolve().parents[1]
GAMES_FIXTURE = ROOT / "tests" / "fixtures" / "valid" / "games.json"


def test_canonical_schema_is_valid():
    schema = load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_game_fixture_passes():
    validate_file(GAMES_FIXTURE)


def test_empty_game_collection_is_valid():
    validate_collection({"schema_version": 1, "updated_at": "2026-11-04T00:00:00Z", "records": []})


def test_invalid_timestamp_is_rejected():
    document = json.loads(GAMES_FIXTURE.read_text(encoding="utf-8"))
    document["updated_at"] = "not-a-timestamp"
    with pytest.raises(ValidationError):
        validate_collection(document)


def test_unexpected_game_field_is_rejected():
    document = json.loads(GAMES_FIXTURE.read_text(encoding="utf-8"))
    document["records"][0]["unexpected"] = True
    with pytest.raises(ValidationError):
        validate_collection(document)


def test_validator_uses_repository_schema_path():
    assert SCHEMA_PATH.is_file()


def test_no_duplicate_root_schema():
    # The canonical schema lives only under src/free_game/schemas/.
    # A second copy at the repository root drifted out of sync before
    # (it lacked offer_end_at) and must not be reintroduced.
    assert not (ROOT / "schemas" / "collection.schema.json").exists()


def test_canonical_schema_includes_offer_end_at():
    schema = load_schema()
    assert "offer_end_at" in schema["$defs"]["Game"]["properties"]
