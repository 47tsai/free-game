# Free Game Architecture

## 1. Project purpose

Free Game is a 4Gamers RSS-driven free-game discovery and claim-tracking service. It reads announcements, extracts game and storefront details, creates or updates catalog records, verifies the offer on the relevant storefront, and sends Discord notifications. It also synchronizes automatic claim results from Free Games Claimer (FGC) and provides a website for browsing offers and manually managing claim status.

The 4Gamers RSS feed is the primary discovery source. Storefront-specific verification is performed only after an RSS item identifies a possible offer. Generic parsing remains available for supported formats and platforms without a dedicated verifier. FGC is a claim-status source, not an offer-discovery source.

## 2. Confirmed architectural decisions

- Repository: `47tsai/free-game` (public).
- GitHub is the primary source-controlled data store. Cloudflare D1 is not part of the initial design.
- GitHub Actions runs scheduled and manually triggered ingestion, synchronization, and notification jobs.
- Python is used for backend collection and processing.
- Cloudflare Workers provides the API boundary and CHIAuth integration.
- GitHub Pages hosts the web frontend.
- Discord is the notification channel.
- FGC reports automatic claim results through ntfy.
- Users can also update their own claim status through the website.
- Public catalog and claim data may be publicly readable. Authentication and authorization are still required for write operations.

## 3. High-level components

### Source adapters

Each integration is isolated behind an adapter contract. An adapter fetches source-specific data and emits raw records with source identity and retrieval metadata.

Initial adapter families:
- Primary discovery source: 4Gamers RSS.
- Storefront verification: platform-specific checks invoked for games discovered through RSS.
- Generic adapter: a configurable fallback for supported RSS/Atom/JSON sources and unknown platforms.
- Claim-status source: FGC/ntfy.

Dedicated adapters handle platform-specific retrieval and parsing. They all emit the same normalized observations for the shared ingestion pipeline. The Generic adapter uses the same contract, but is deliberately conservative: it may ingest configured RSS/Atom feeds, JSON feeds, or explicitly configured page parsers where the format is understood. It must preserve source evidence and mark uncertain results as candidates or unresolved observations. It must not invent product identifiers, offer deadlines, or claim that an offer is verified without adequate storefront evidence. Unsupported or ambiguous formats remain stored as raw source records for later parser work or manual review.

The Generic adapter is a fallback, not a replacement for dedicated adapters. Once a source has stable, platform-specific behavior or requires specialized identity, pagination, authentication, or offer semantics, it should receive a dedicated adapter.

A source must not be treated as authoritative for fields it does not provide. Missing or unknown deadlines must remain explicitly unknown rather than being fabricated.

### Ingestion pipeline

1. A source runner fetches the response using bounded timeouts, response-size limits, HTTPS checks, and redaction of sensitive query parameters. GitHub JSON writes use separate bounded SHA-conflict retries.
2. The adapter parses source-specific fields into source observations.
3. The adapter normalizes observations into platform-independent candidates.
4. The shared IngestionPipeline validates candidate shape, timestamps, URLs, source identity, and same-run duplicate source records.
5. A later catalog reconciliation stage matches or proposes Game, Product, and Offer records, then verifies offers against authoritative storefront evidence.
6. A repository writer persists accepted changes to GitHub JSON with optimistic concurrency and idempotent updates.
7. Domain events are emitted for notification evaluation.

The current Python implementation covers the adapter contract, 4Gamers RSS keyword filtering and article-page storefront-link extraction, Generic RSS/Atom/JSON parsing, a configuration-driven SourceRegistry, a bounded HTTPFetcher, a per-source-isolated SourceRunner, an idempotent GitHubJsonWriter, and conservative Product-to-Game reconciliation. The runner fetches enabled sources, records response metadata and a payload hash, then passes bytes to the side-effect-free parse/normalize/validate/deduplicate pipeline. The CLI fetches each matching 4Gamers article page and extracts recognized storefront links into platform-specific Product candidates; articles without a recognized link remain discovery records. The writer persists source provenance and platform Product identities with deterministic UUIDv5 IDs, collection schema validation, GitHub Contents API blob-SHA checks, and bounded conflict retries. A conservative reconciliation pass creates one provisional Game per Product and links it without merging across platforms based on title similarity. Authoritative claimability verification, Offer creation, and notification delivery remain separate implementation stages. The pipeline returns observations, accepted candidates, and structured issues; it does not write data or mark offers as verified.

A failure in one adapter should not prevent successful adapters from completing. Raw source evidence and parse errors should be retained where practical for diagnosis. The Generic adapter follows the same isolation and validation rules; a generic parse result must never bypass the common verification and validation pipeline.

### Core domain

- Game: the conceptual game or work.
- Product: a platform-specific listing or entitlement target.
- Offer: one time-bounded or ongoing free promotion for a product.
- Claim: a user's claim status for a product or offer, with source and timestamps.
- Notification: a record of a notification attempt and its idempotency key.
- SourceRecord: provenance linking normalized data to the source record that supplied it.

Game and Product must be separate because one game can have multiple storefront listings and platform-specific claim states.

### Services

- Catalog service: game, product, and offer matching and updates.
- Claim service: the only application-level entry point for claim mutations.
- Notification service: Discord delivery, deduplication, retry, and delivery logs.
- FGC receiver: validates and normalizes ntfy events before passing them to the Claim service.
- API service: public catalog reads and authenticated user operations.

## 4. Storage model and write ownership

GitHub JSON files are the initial persistence layer. Data is split by responsibility rather than placed in one large document.

Proposed logical groups:
- Public catalog: games, products, offers, and source metadata.
- Claim records: claim status keyed by user and product/offer.
- Operational state: ingestion cursors, processed source IDs, notification idempotency records, and FGC event cursors.

The exact file layout and schemas are specified in DATA_MODEL.md before implementation.

All writes must go through a controlled writer abstraction. GitHub's file API is not a transactional database and concurrent read-modify-write operations can conflict or overwrite each other. Therefore:
- Avoid independent writers mutating the same JSON file.
- Use GitHub concurrency groups for Actions jobs that write shared state.
- Use blob SHA / expected-version checks and retry with a fresh read on conflicts.
- Keep write batches small and split high-churn operational state from catalog data.
- Make ingestion and notification jobs idempotent so a retry does not create duplicate offers or messages.

The public repository means all committed data and its history are public. Never store access tokens, passwords, private webhook URLs, session data, or other secrets in repository JSON or generated public assets. Public claim data is an explicit product decision, not a substitute for authorization.

## 5. API and identity boundary

Cloudflare Workers is the only public write boundary for website-originated user changes. It integrates with CHIAuth, validates the authenticated identity, and enforces that a user can only modify records belonging to that identity.

The frontend must never receive a GitHub token with write permissions. Any GitHub credential used by the Worker is stored as a Worker secret and scoped as narrowly as practical.

FGC/ntfy events use a separate authenticated ingestion path. A public or guessable ntfy topic alone is not sufficient authorization to mutate claim records. Events should be validated, deduplicated, mapped to a platform product, and then processed by the Claim service.

The initial deployment may use one FGC account, while the data model should include a stable user identifier so additional users or integrations can be supported without redesigning the claim entity.

## 6. Frontend and public data

GitHub Pages serves the static website. Public catalog data can be published as JSON snapshots for efficient browsing. User-specific mutations and authenticated reads go through the Worker API.

The UI should support:
- Browse and search games and offers.
- Filter by platform, offer status, and deadline availability.
- View platform-specific product links.
- Sign in through CHIAuth.
- View and manually update the signed-in user's claim status.

Public read access to claim records is allowed by the current project decision. Write access remains authenticated and owner-scoped.

## 7. Scheduling and notifications

GitHub Actions is the initial scheduler and execution environment. Jobs should be independently runnable and safe to retry.

Suggested job responsibilities:
- Discovery: fetch and normalize new offers.
- Refresh: update existing offer details and status.
- FGC synchronization: consume claim events and update claim records.
- Reminder evaluation: identify offers approaching their deadlines.
- Notification delivery: send eligible Discord messages and record delivery outcomes.

Exact schedules are configuration decisions and should be documented separately. Do not assume every source supports the same polling frequency or deadline semantics.

Notification idempotency keys should include the offer and notification type. Failed deliveries should be retryable without repeating already successful notifications.

## 8. Reliability and observability

- Isolate source failures.
- Preserve unknown values rather than inventing data.
- Record fetch, parse, validation, and persistence errors.
- Make all scheduled jobs safe to rerun.
- Track notification attempts and FGC event cursors.
- Back up important JSON data and document restore procedures.
- Validate schemas in CI before data is committed or deployed.

## 9. Delivery phases

1. Finalize data entities, identifiers, JSON schemas, and write ownership.
2. Implement the Python core and test fixtures.
3. Add source adapters incrementally, beginning with the most reliable sources.
4. Add Discord notification and idempotency.
5. Add FGC event ingestion and the shared Claim service.
6. Add Worker API and CHIAuth authorization.
7. Add the GitHub Pages frontend and manual claim controls.
8. Add operational monitoring, backup, and recovery procedures.

## 10. Explicit non-goals for the initial version

- No Cloudflare D1 dependency.
- No microservices architecture.
- No direct browser writes to GitHub.
- No assumption that every platform exposes a stable public API.
- No migration of legacy data until the new schemas and behavior are tested.
