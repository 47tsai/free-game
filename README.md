# Free Game

A 4Gamers RSS-driven free-game collector.

## Flow

1. Fetch the 4Gamers latest-news RSS feed every six hours.
2. Select free-game articles and read their article pages.
3. Extract game titles, storefronts, and claim links from the article.
4. Save the results to GitHub JSON.
5. Send each newly discovered game to Discord once when `DISCORD_WEBHOOK_URL` is configured.

4Gamers is the source of truth for its curated free-game information. The project does not query storefront APIs to re-verify those offers.

## Development

Requires Python 3.12 or newer.

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Run manually:

```bash
free-game ingest --config config/sources.json
```

GitHub Actions runs ingestion every six hours and supports manual dispatch. Add `DISCORD_WEBHOOK_URL` as a repository Actions secret to enable Discord notifications. GitHub Actions provides `GITHUB_TOKEN` for JSON persistence.

The repository keeps the parsed source records and extracted storefront product records as JSON. It does not perform Epic/Steam/storefront verification, cross-platform game matching, account linking, or claim automation.
