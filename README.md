# Free Game

A multi-platform free-game discovery and claim-tracking project.

## Project status

The repository currently contains the initial architecture and data contracts, a Python package scaffold, JSON Schema validation, test fixtures, and a GitHub Actions validation workflow. Storefront adapters and production API services have not been implemented yet.

## Development

Requires Python 3.12 or newer.

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The canonical persisted-data schema is in `schemas/collection.schema.json`. The validator is available from `free_game.validation`.

## Design documents

- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [API contract](docs/API.md)
- [Source integration contracts](docs/SOURCES.md)
- [Schema validation notes](schemas/README.md)

## Current boundaries

- GitHub is the initial JSON persistence layer; Cloudflare D1 is not used.
- GitHub Actions runs scheduled and CI workloads.
- Cloudflare Workers is the intended API and CHIAuth boundary.
- GitHub Pages is the intended frontend host.
- Secrets and private account credentials must never be committed to this public repository.
