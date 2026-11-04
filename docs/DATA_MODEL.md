# Free Game Data Model

This document defines the canonical entities and JSON persistence contract for the initial Free Game implementation. It complements [ARCHITECTURE.md](./ARCHITECTURE.md).

## 1. Design principles

1. Separate a conceptual game from each storefront's product/listing and from each promotion.
2. A game may have many products; a product may have many offers over time.
3. Claim state belongs to a user and a platform product. It must not be inferred from whether an offer is currently active.
4. Preserve source provenance. Do not silently replace a known value with a weaker or unknown value from another source.
5. Unknown deadlines and uncertain game matches are valid states. Never invent a deadline or merge two games solely because their names look similar.
6. Use stable identifiers and idempotent upserts so repeated ingestion does not create duplicates.
7. Keep public catalog data, user claim data, and high-churn operational state in separate files.

## 2. Identifier conventions

All internal IDs are opaque strings and must remain stable after creation.

Recommended forms:
- `game_id`: `game_<uuid>`
- `product_id`: `product_<uuid>`
- `offer_id`: `offer_<uuid>`
- `claim_id`: deterministic composite key or opaque ID derived from `user_id + product_id`
- `source_record_id`: stable source namespace plus source's external record identifier
- `notification_id`: opaque ID; idempotency is enforced separately by a deterministic key

Platform identifiers must be namespaced. For example, Steam App ID `12345` and a GOG product ID `12345` are different products.

Recommended natural key for a product:
`platform + external_product_id`

Recommended natural key for an offer:
`platform + external_offer_id` when the platform supplies a stable offer ID. Otherwise use a stable source-specific key derived from the product, source, and promotion identity. Do not use a mutable title or deadline alone as the identity.

UUID generation strategy must be consistent across all writers. A record must not receive a new internal ID merely because it was rediscovered by another source.

## 3. Canonical entities

### 3.1 Game

A conceptual game or work, independent of storefront.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | string | yes | Stable internal game ID |
| `title` | string | yes | Display title |
| `normalized_title` | string | yes | Matching/search helper, not a unique key |
| `description` | string or null | no | Short description |
| `cover_image_url` | string or null | no | Public image URL |
| `developers` | string[] | no | Developer names |
| `publishers` | string[] | no | Publisher names |
| `genres` | string[] | no | Optional genre labels |
| `created_at` | ISO-8601 UTC string | yes | Creation time |
| `updated_at` | ISO-8601 UTC string | yes | Last modification time |
| `source_record_ids` | string[] | no | Provenance references |

A game is a cross-platform grouping, not a storefront listing. If two records cannot be confidently matched, keep separate Game records until reviewed.

### 3.2 Product

A platform-specific listing or entitlement target.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | string | yes | Stable internal product ID |
| `game_id` | string or null | yes | Related game; null when not confidently matched |
| `platform` | string | yes | Canonical platform key |
| `external_product_id` | string | yes | Platform's product identifier |
| `title` | string | yes | Storefront title |
| `product_url` | string | yes | Canonical product/store URL |
| `region` | string or null | no | Region restriction, if known |
| `edition` | string or null | no | Edition or package detail |
| `created_at` | ISO-8601 UTC string | yes | Creation time |
| `updated_at` | ISO-8601 UTC string | yes | Last modification time |
| `source_record_ids` | string[] | no | Provenance references |

Initial platform keys: `steam`, `epic`, `gog`, `ubisoft`, `dlsite`. The set is extensible; consumers must tolerate unknown platform keys.

One conceptual Game can have multiple Products. A Product must belong to no more than one Game at a time. Product identity is platform-scoped.

### 3.3 Offer

One free promotion or claim opportunity for a Product.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | string | yes | Stable internal offer ID |
| `product_id` | string | yes | Target Product |
| `platform` | string | yes | Denormalized platform key for filtering |
| `source_record_ids` | string[] | yes | Evidence supporting this offer |
| `title` | string | yes | Offer display title |
| `claim_url` | string or null | no | Direct claim/promotion URL |
| `starts_at` | ISO-8601 UTC string or null | no | Known start time |
| `ends_at` | ISO-8601 UTC string or null | no | Known end time |
| `deadline_status` | enum | yes | `known`, `unknown`, or `not_applicable` |
| `status` | enum | yes | `upcoming`, `active`, `ended`, or `unknown` |
| `verification_status` | enum | yes | `candidate`, `verified`, `needs_review`, or `rejected` |
| `region` | string or null | no | Region applicability, if known |
| `terms` | string or null | no | Important claim restrictions |
| `first_seen_at` | ISO-8601 UTC string | yes | First discovery time |
| `last_seen_at` | ISO-8601 UTC string | yes | Most recent confirmation |
| `created_at` | ISO-8601 UTC string | yes | Record creation time |
| `updated_at` | ISO-8601 UTC string | yes | Last modification time |

Rules:
- Only a storefront-verified Offer may enter the public offer collection or notification flow.
- `verification_status` is independent of the time-based `status`; a verified offer may be upcoming, active, or ended.
- `deadline_status=known` requires a valid `ends_at`.
- `deadline_status=unknown` means the source did not provide a trustworthy deadline. Do not reject the offer solely because its deadline is unknown.
- `deadline_status=not_applicable` is for genuinely non-time-limited offers.
- `status` is derived from trusted timestamps and source evidence. If the available evidence is insufficient, use `unknown`.
- An expired offer is historical data, not a reason to delete the record.
- A recurring promotion creates a new Offer when it represents a distinct claim window. Do not overwrite historical claim windows.

### 3.4 Claim

A user's claim/ownership state for a platform Product. Claim state is product-scoped so that a successful claim remains meaningful after the promotion ends or a later promotion begins.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | string | yes | Stable claim ID |
| `user_id` | string | yes | CHIAuth subject identifier |
| `product_id` | string | yes | Platform Product |
| `status` | enum | yes | `claimed`, `unclaimed`, or `unknown` |
| `source` | enum | yes | `fgc`, `manual`, or `import` |
| `claimed_at` | ISO-8601 UTC string or null | no | Known claim time |
| `updated_at` | ISO-8601 UTC string | yes | Last state change |
| `note` | string or null | no | Optional user note |

Natural uniqueness constraint: one current Claim per `user_id + product_id`.

Rules:
- FGC and the website must call the same Claim service / mutation rules.
- A manual update must not be overwritten by a stale FGC event.
- An FGC failure is an event/attempt, not proof that the user does not own the product. Do not set Claim status to `failed`.
- Unknown and unclaimed are distinct. Unknown means no reliable state has been established.
- The authenticated identity must be taken from verified CHIAuth claims, never from a client-supplied `user_id` field.

### 3.5 ClaimEvent

Append-only record of claim-related events, including FGC success/failure and manual changes.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | string | yes | Stable event ID |
| `user_id` | string | yes | Associated user |
| `product_id` | string | yes | Associated Product |
| `offer_id` | string or null | no | Related promotion, if known |
| `event_type` | enum | yes | `claim_succeeded`, `claim_failed`, `manual_marked_claimed`, `manual_marked_unclaimed`, `state_imported` |
| `source` | enum | yes | `fgc`, `manual`, or `import` |
| `occurred_at` | ISO-8601 UTC string | yes | Event time |
| `received_at` | ISO-8601 UTC string | yes | Ingestion time |
| `external_event_id` | string or null | no | Upstream event ID for deduplication |
| `details` | object | no | Sanitized non-secret diagnostic metadata |

ClaimEvent is append-only. Never place credentials, session tokens, or private account data in `details`.

### 3.6 Notification

A delivery attempt for a particular event and channel.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | string | yes | Stable notification record ID |
| `offer_id` | string | yes | Related Offer |
| `notification_type` | enum | yes | `new_offer`, `deadline_reminder`, `offer_updated` |
| `channel` | string | yes | Initial value: `discord` |
| `idempotency_key` | string | yes | Unique logical notification key |
| `status` | enum | yes | `pending`, `sent`, or `failed` |
| `attempt_count` | integer | yes | Number of delivery attempts |
| `created_at` | ISO-8601 UTC string | yes | First queued time |
| `sent_at` | ISO-8601 UTC string or null | no | Successful delivery time |
| `last_error` | string or null | no | Sanitized last error |

The idempotency key should include the Offer ID, notification type, and relevant reminder window. A successful notification must not be sent again merely because a workflow reruns.

### 3.7 SourceRecord

Provenance for a source observation.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | string | yes | Stable source record ID |
| `source` | string | yes | Adapter/source key |
| `external_id` | string | yes | Source's record identifier |
| `record_type` | enum | yes | `discovery`, `store_product`, `store_offer`, or `claim_event` |
| `url` | string or null | no | Source record URL |
| `first_seen_at` | ISO-8601 UTC string | yes | First observation |
| `last_seen_at` | ISO-8601 UTC string | yes | Latest observation |
| `content_hash` | string or null | no | Hash of normalized source payload |
| `linked_entity_ids` | string[] | no | Related Game/Product/Offer IDs |

Do not store unbounded raw HTML or large payloads in the main catalog files. If raw evidence is retained, store it separately with size limits and retention rules.

## 4. JSON file layout

Initial proposed layout:

```text
data/
├── catalog/
│   ├── games.json
│   ├── products.json
│   ├── offers.json
│   └── source-records.json
├── claims/
│   ├── claims.json
│   └── claim-events.json
└── operations/
    ├── notifications.json
    ├── processed-records.json
    ├── source-cursors.json
    └── ntfy-cursor.json
```

Each collection file uses a versioned envelope:

```json
{
  "schema_version": 1,
  "updated_at": "2026-11-04T00:00:00Z",
  "records": []
}
```

The envelope's `records` array contains entities of exactly one type. Empty collections are valid. Files must be UTF-8 JSON and validated in CI.

This layout is a starting point. If a collection grows enough to cause frequent large commits or merge conflicts, shard it by stable key (for example, by platform or ID prefix) without changing the entity schema.

## 5. Data update and conflict rules

GitHub Contents API writes are versioned by blob SHA and are not transactional across multiple files.

- A writer reads the latest file and its blob SHA before updating.
- On a conflict, it rereads, reapplies the intended idempotent change, and retries with a bounded retry count.
- Actions that mutate the same state use a shared concurrency group.
- Avoid having an Actions workflow and Worker independently perform read-modify-write on the same JSON file at the same time.
- Multi-file changes are not atomic. Write dependent records in a safe order and make readers tolerate temporarily missing references.
- Never delete historical Offers or ClaimEvents as routine cleanup.
- Operational cursors advance only after the corresponding events have been durably processed.

## 6. Validation requirements

The schema/test suite should verify at minimum:

- IDs are non-empty and unique within each collection.
- Product `platform + external_product_id` is unique.
- Claim `user_id + product_id` is unique.
- Offer references an existing Product.
- Product's `game_id`, when non-null, references an existing Game.
- All timestamps are valid ISO-8601 values normalized to UTC.
- Known deadlines have an `ends_at` value.
- Unknown deadlines are allowed.
- URLs use allowed schemes (normally HTTPS).
- Notification idempotency keys are unique.
- Claim mutations are owner-scoped and use verified identities.
- Source adapter data cannot directly overwrite claim state.

## 7. Decisions intentionally deferred

The following require implementation-level evidence or a separate decision:
- Exact JSON Schema dialect and whether schemas are maintained as separate files.
- Whether claims are indexed in one collection or sharded by user ID.
- Retention period and size limit for ClaimEvents, Notification records, and SourceRecords.
- Exact FGC event payload mapping and external event ID availability.
- Whether platform product matching can use official cross-store identifiers.
- How ambiguous game merges are reviewed or reversed.


## 8. Current writer behavior

The initial `GitHubJsonWriter` persists only `Product` and `SourceRecord` collections:

- Product identity is deterministic UUIDv5 over the canonical `platform + external_product_id` pair. Rediscovery therefore reuses the same Product ID across runs and across sources.
- SourceRecord identity is deterministic UUIDv5 over `source_key + source_external_id`.
- A candidate without a reliable platform product identity may still be retained as a `discovery` SourceRecord when it has a source external ID. It does not create a Product.
- Candidate records with no source external ID are skipped because the current SourceRecord schema requires one.
- New Products begin with `game_id: null`. The writer does not merge conceptual Games by title.
- Unverified candidates never create Offers. An Offer requires a separate authoritative verification stage.
- Product and SourceRecord provenance links are accumulated idempotently. Existing first-seen and creation timestamps are preserved.
- Collection writes validate against the canonical JSON Schema before calling GitHub Contents API.
- On a blob-SHA conflict, the writer rereads the latest collection, reapplies the deterministic upsert, and retries a bounded number of times.

The Products and SourceRecords files are written separately because GitHub Contents API does not provide multi-file transactions. A workflow rerun safely completes a partially applied pair of writes. The writer does not advance source cursors; cursor advancement must happen only after all required collection writes have succeeded.


## 9. Initial Product-to-Game reconciliation

The current writer creates a provisional Game for each Product that does not yet reference a Game. The provisional Game ID is deterministic from the Product ID, and the Product is updated to reference it.

This is intentionally a one-to-one starting point, not cross-platform deduplication:

- Products on different platforms are never merged merely because their titles match.
- Title normalization uses Unicode NFKC, case folding, and punctuation/whitespace normalization. It is descriptive metadata, not proof of identity.
- Existing Game links are preserved. The writer does not silently move a Product between Games.
- SourceRecord IDs are copied to the provisional Game as provenance.
- A future reviewed mapping operation may link multiple Products to one canonical Game. It must preserve the old IDs or provide an explicit migration plan for any existing references.

The writer persists the Game collection before updating Product.game_id. If the Product update fails, the unreferenced Game is harmless and the next run can safely finish the link. This is necessary because GitHub Contents API does not support atomic multi-file commits through the current writer.
