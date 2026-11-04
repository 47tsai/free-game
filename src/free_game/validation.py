"""Validation helpers for persisted Free Game JSON collections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "collection.schema.json"
_FORMAT_CHECKER = FormatChecker()


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    """Load and validate the canonical collection schema."""
    with path.open("r", encoding="utf-8") as schema_file:
        schema = json.load(schema_file)

    Draft202012Validator.check_schema(schema)
    return schema


def validate_collection(
    document: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
) -> None:
    """Raise jsonschema.ValidationError when a collection is invalid."""
    active_schema = schema if schema is not None else load_schema()
    validator = Draft202012Validator(
        active_schema,
        format_checker=_FORMAT_CHECKER,
    )
    validator.validate(document)


def validate_file(path: Path, *, schema: dict[str, Any] | None = None) -> None:
    """Load a JSON file and validate it as one canonical collection."""
    with path.open("r", encoding="utf-8") as data_file:
        document = json.load(data_file)

    validate_collection(document, schema=schema)
