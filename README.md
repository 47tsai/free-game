# Free Game

A multi-platform free-game discovery and claim-tracking project.

## Project status

The repository now includes:
- A configuration-driven source registry and Generic RSS/Atom/JSON adapter.
- A dedicated Steam featured-categories candidate adapter.
- A bounded, per-source-isolated HTTP ingestion runner.
- A shared parse/normalize/validate/deduplicate pipeline.
- An idempotent GitHub JSON writer for Product and SourceRecord collections.
- Deterministic identifiers, JSON Schema validation, SHA conflict retries, and automated tests.

No production source is enabled in `config/sources.json` yet. Candidates are not Offers: authoritative storefront verification and catalog reconciliation must be implemented before free promotions can be published or notifications sent.

## Development

Requires Python 3.12 or newer.

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Run the configured ingestion command:

```bash
free-game ingest --config config/sources.json
```

The command exits successfully without network requests when no sources are enabled. When enabled sources produce persistable candidates, set `GITHUB_TOKEN` (or `GH_TOKEN`) with repository Contents write permission. The command fetches enabled sources and persists only Product identities and SourceRecord provenance. It does not create Games or Offers, advance cursors, or send notifications.

The canonical persisted-data schema is in `schemas/collection.schema.json`. Use `free_game.validation` to validate one collection's structure, and `free_game.semantic_validation.validate_dataset` to validate references and uniqueness across a mapping of collection names to collection documents.

## Design documents

- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [API contract](docs/API.md)
- [Source integration contracts](docs/SOURCES.md)
- [Schema validation notes](schemas/README.md)

## Current boundaries

- GitHub is the initial JSON persistence layer; Cloudflare D1 is not used.
- GitHub Actions runs CI; a production ingestion schedule is not enabled yet.
- Cloudflare Workers is the intended API and CHIAuth boundary.
- GitHub Pages is the intended frontend host.
- Secrets and private account credentials must never be committed to this public repository.
