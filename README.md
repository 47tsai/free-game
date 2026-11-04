# Free Game

A 4Gamers RSS-driven free-game discovery and claim-tracking project.

## Project status

The repository now includes:
- A 4Gamers RSS adapter that selects free-game announcements from the latest-news feed.
- A configuration-driven source registry and Generic RSS/Atom/JSON adapter.
- A bounded, per-source-isolated HTTP ingestion runner.
- A shared parse/normalize/validate/deduplicate pipeline.
- An idempotent GitHub JSON writer for Product, Game, and SourceRecord collections.
- Conservative Product-to-Game reconciliation that creates one provisional Game per Product without unsafe cross-platform title merges.
- Exact-match Epic promotion verification for active Taiwan-region zero-price offers, with only verified results eligible for Offer persistence.
- Idempotent Discord notifications for verified active offers, with delivery state recorded in GitHub JSON.
- Deterministic identifiers, JSON Schema validation, SHA conflict retries, and automated tests.

The configured primary source is 4Gamers latest-news RSS. The current ingestion run filters articles by free-game keywords, fetches matching article pages, extracts supported storefront links, and writes Product/Game/SourceRecord data to GitHub JSON. Epic active promotions are now checked against the Taiwan storefront promotion feed. Steam and other platforms remain unverified until their own evidence can prove claimability. Discord notifications are sent once per verified active Offer when `DISCORD_WEBHOOK_URL` is configured. Delivery state is recorded before sending to prevent duplicates. Generic RSS/Atom/JSON parsing remains available for explicitly configured sources and unknown platforms.

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

The command exits successfully without network requests when no sources are enabled. When enabled sources produce persistable candidates, set `GITHUB_TOKEN` (or `GH_TOKEN`) with repository Contents write permission. The command fetches enabled sources, analyzes matching 4Gamers article pages, persists extracted Product identities and SourceRecord provenance, and creates provisional Game links. It does not merge products across platforms or advance source cursors. When `DISCORD_WEBHOOK_URL` is configured, it sends one Discord notification per verified active Offer and records the result in `data/operations/notifications.json`. Add that value as a repository Actions secret to enable Discord delivery. It creates Offer records only when the Epic verifier confirms an exact product match, an active promotion, and a zero promotional price.

The canonical persisted-data schema is in `schemas/collection.schema.json`. Use `free_game.validation` to validate one collection's structure, and `free_game.semantic_validation.validate_dataset` to validate references and uniqueness across a mapping of collection names to collection documents.

## Design documents

- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [API contract](docs/API.md)
- [Source integration contracts](docs/SOURCES.md)
- [Schema validation notes](schemas/README.md)

## Current boundaries

- GitHub is the initial JSON persistence layer; Cloudflare D1 is not used.
- GitHub Actions runs CI and the ingestion workflow every six hours, with manual dispatch available.
- Cloudflare Workers is the intended API and CHIAuth boundary.
- GitHub Pages is the intended frontend host.
- Secrets and private account credentials must never be committed to this public repository.
