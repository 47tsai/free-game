# JSON Schema Validation

## Canonical schema

- `collection.schema.json` validates the versioned collection envelope and the seven entity collection types defined in `docs/DATA_MODEL.md`.
- Dialect: JSON Schema Draft 2020-12.
- Current envelope version: `schema_version: 1`.

The schema accepts one homogeneous record type per collection. Empty collections are valid. The root uses `anyOf` so an empty `records` array can validate without failing an ambiguous `oneOf` match.

## Intended file mapping

| Data file | Record definition |
|---|---|
| `data/catalog/games.json` | `Game` |
| `data/catalog/products.json` | `Product` |
| `data/catalog/offers.json` | `Offer` |
| `data/catalog/source-records.json` | `SourceRecord` |
| `data/claims/claims.json` | `Claim` |
| `data/claims/claim-events.json` | `ClaimEvent` |
| `data/operations/notifications.json` | `Notification` |

## Validation boundaries

JSON Schema checks document shape, required fields, primitive types, enumerated values, timestamp formats, HTTPS URL shape, and the Offer deadline rule.

It does not by itself enforce collection-wide or cross-file constraints. A later semantic validation step must check at least:

- Unique entity IDs within each collection.
- Unique `platform + external_product_id` pairs.
- Unique `user_id + product_id` Claim pairs.
- Unique Notification `idempotency_key` values.
- Product-to-Game and Offer-to-Product references.
- Timestamp normalization to UTC (the schema checks date-time syntax, not timezone policy).
- Claim ownership and authorization rules.
- Append-only behavior for ClaimEvents.
- FGC event deduplication and stale-event/manual-update precedence.

Validators must enable JSON Schema format assertion for `date-time` and `uri`; implementations that treat formats as annotations only are insufficient for CI validation.

## Compatibility policy

- Keep `schema_version` explicit.
- A breaking persisted-data change requires a schema version decision and a migration plan before rollout.
- Do not silently loosen required fields or enum values to accommodate malformed source data. Normalize or quarantine source observations instead.
- Unknown platform strings remain valid so new storefronts can be added without changing the schema for every platform.
- Never place secrets, session cookies, access tokens, or private account data in fixtures or committed JSON.
