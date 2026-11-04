# Source Integration Contracts

> Status: initial design. Concrete endpoints, authentication requirements, and collection permissions must be verified before implementation. This document defines how source data enters the system; it does not claim that every platform provides a supported public API.

## 1. Source categories and responsibilities

Sources are divided by the kind of evidence they provide. A source must not be treated as authoritative outside its assigned responsibility.

| Source | Category | Primary responsibility | Not responsible for |
|---|---|---|---|
| Steam | Storefront adapter | Discover and verify Steam products and promotional offers | Claim ownership state unless a separately verified integration provides it |
| Epic Games Store | Storefront adapter | Discover and verify Epic products and promotional offers | User claim state |
| GOG | Storefront adapter | Discover and verify GOG products and promotional offers | User claim state |
| Ubisoft | Storefront adapter | Discover and verify Ubisoft products and promotional offers | User claim state |
| DLsite | Storefront adapter | Discover and verify relevant product and campaign information | Inferring that an age warning alone means a listing is adult content |
| 4Gamers RSS | Discovery/editorial source | Surface possible free-game announcements for investigation | Final offer truth, product identity, or claim state |
| Generic adapter | Configurable fallback adapter | Ingest supported feeds or explicitly configured structured sources for platforms without a dedicated adapter | Guessing unsupported formats, product identity, offer deadlines, or verified offer state |
| FGC via ntfy | Claim-status integration | Report claim attempts and observed claim outcomes | Discovering storefront offers |

### 1.1 Storefront adapters

A storefront adapter is responsible for collecting observations about products and offers from its platform. Prefer documented, supported interfaces where available. If an official API or feed is unavailable, any alternative collection method must be separately reviewed for reliability, access conditions, and operational constraints.

Do not assume that a platform has a stable public API. Before implementation, record the selected access method and verify its current behavior against official documentation or a controlled fixture.

### 1.2 Discovery sources

Discovery sources provide leads, not canonical offer records. A 4Gamers item may identify a game or promotion worth checking, but the corresponding storefront must be checked before an offer is published as verified.

### 1.3 Generic fallback adapter

The Generic adapter is the fallback path for an otherwise unsupported platform or source. It must use an explicitly configured source definition; it is not an unrestricted web crawler and must not guess how an unknown site works.

Initial supported input types should be limited to formats with predictable structure, such as RSS/Atom and JSON. A page-specific HTML parser may be enabled only when its selectors and behavior have been reviewed and covered by fixtures. The Generic adapter should:

- Assign a stable, namespaced source key to each configured source.
- Preserve the original source URL, external identifiers, retrieval time, and sanitized raw evidence.
- Extract only fields that are directly supported by the source.
- Emit unresolved or candidate observations when product identity, platform, price, or offer dates are ambiguous.
- Pass all normalized candidates through the same validation, matching, and storefront-verification pipeline as dedicated adapters.
- Never fabricate platform product IDs, deadlines, or claim outcomes.
- Retain unsupported records with parse warnings for later manual review or a dedicated adapter.

The Generic adapter does not automatically make an unknown platform eligible for FGC claim synchronization. Claim synchronization requires a separately verified platform/product mapping and an explicit integration contract.

A dedicated adapter should replace the generic path when a source needs platform-specific authentication, pagination, identity rules, offer semantics, or more reliable parsing. Both paths must continue to emit the same platform-independent domain entities.

### 1.4 Claim-status provider

FGC reports claim activity and outcomes. Its events must be reconciled against known users and platform products. An FGC failure event is evidence of an unsuccessful attempt, not proof that the product is unclaimed.

## 2. Canonical adapter contract

Each adapter should expose a small, platform-independent interface. The implementation language may differ, but its output must be normalized before it reaches the domain layer.

Conceptual interface:

```text
SourceAdapter
  source_key
  fetch(context) -> FetchResult
  parse(raw_response) -> list[SourceObservation]
  normalize(observation) -> list[NormalizedCandidate]
```

Fetching is runner-owned rather than required on each adapter, so all sources can share network timeouts, retries, and credential redaction. The current Python adapter protocol exposes `source_key`, `parse(payload)`, and `normalize(observations)`. The shared `IngestionPipeline` invokes those stages and returns observations, accepted candidates, and structured validation/deduplication issues. It does not fetch, persist, reconcile catalog entities, or verify offers.

A source runner may record a `FetchResult` carrying:

- `source_key`: stable source identifier, such as `steam` or `4gamers`.
- `fetched_at`: UTC timestamp when the response was retrieved.
- `request_url`: requested URL, with secrets and sensitive query parameters removed.
- `http_status`: response status when applicable.
- `payload_hash`: hash of the retained raw payload or canonicalized response.
- `parser_version`: version of the parser that interpreted the payload.
- `observations`: zero or more source observations.
- `warnings`: non-fatal parsing or data-quality warnings.

A `SourceObservation` should preserve source evidence rather than silently replacing it with inferred values:

- `source`
- `external_id`, when supplied by the source
- `observed_at`
- `source_url`
- `raw_title`
- `raw_description`, when available
- `raw_price` and `raw_currency`, when available
- `raw_start_at` and `raw_end_at`, when available
- `payload_hash`
- `raw_data_ref` or a bounded raw excerpt, subject to storage and retention policy

Secrets, cookies, authorization headers, and personal account data must never be stored in source observations or committed to the repository.

## 3. Identity and normalization

### 3.1 Product identity

A platform product is identified by the pair:

```text
(platform, external_product_id)
```

The external ID must come from the platform or a verified platform URL mapping. Do not use a title as a product identifier.

### 3.2 Cross-platform game identity

A `Game` represents the conceptual game across storefronts. A `Product` represents a platform-specific listing. One game may map to multiple products.

Cross-platform matching must be conservative:

1. Exact, verified identifiers or an explicit trusted mapping may be linked automatically.
2. Strong title matches may be proposed for review, but must not silently merge products.
3. Similar titles, editions, bundles, remasters, DLC, and regional variants must remain distinct until their relationship is established.
4. Preserve the source evidence and the reason for every non-trivial mapping.

A failed match should remain unresolved rather than creating a false association.

### 3.3 Offer identity

An offer is a time-bounded or otherwise explicitly defined promotion for a product. Its identity should be stable across repeated fetches. Prefer a platform campaign or offer ID when one exists; otherwise use a deterministic key derived from the platform product and verified campaign attributes.

A changed end date or price should update the relevant offer observation/history, not create duplicate offers on every fetch.

## 4. Offer verification and deadline semantics

A storefront adapter may report a candidate offer. The ingestion pipeline should distinguish:

- `candidate`: discovered but not yet verified.
- `verified`: supported by current storefront evidence.
- `expired`: the source provides evidence that the offer has ended.
- `unavailable`: the product or offer can no longer be confirmed.
- `unknown`: evidence is insufficient to determine the state.

Do not invent an offer deadline. Represent deadline knowledge explicitly:

- `known`: a trustworthy end timestamp was observed.
- `unknown`: no reliable deadline is available.
- `not_applicable`: the offer has no meaningful deadline.

If a deadline is unknown, do not reject or hide an otherwise valid offer solely because a deadline is missing. The UI should communicate uncertainty rather than display a fabricated date.

When sources disagree, prefer current storefront evidence for the storefront's own offer. Preserve conflicting observations for diagnosis instead of silently overwriting them.

## 5. Source-specific collection plans

The following table is an implementation checklist, not a claim that the listed access methods have already been verified.

| Source | Data to collect | Access method status | Verification requirement |
|---|---|---|---|
| Steam | Product identity, title, product URL, price, promotion state, offer dates when available | To be researched and verified | Confirm the product page or supported platform response |
| Epic Games Store | Product identity, title, product URL, free/discounted state, promotion dates | To be researched and verified | Confirm current offer against the storefront |
| GOG | Product identity, title, product URL, price, promotion state, dates | To be researched and verified | Confirm current offer against the storefront |
| Ubisoft | Product identity, title, product URL, promotion state, dates | To be researched and verified | Confirm current offer against the storefront |
| DLsite | Product identity, title, product URL, price, campaign state, dates where available | To be researched and verified | Confirm the listing and campaign on DLsite; do not infer content category from an age-warning label alone |
| 4Gamers RSS | Article ID, title, URL, publication time, extracted game/platform references | RSS feed and feed format must be verified | Resolve the article to a storefront product and verify the offer there |
| Generic configured source | Source ID, external ID when available, title, URL, directly observed offer fields, raw evidence reference | Per-source feed or parser configuration; only supported formats are enabled | Confirm source identity, parser behavior, product mapping, and storefront evidence before publishing a verified offer |
| FGC / ntfy | Event ID, platform, external product reference, event type, event time, execution result | Existing deployment payload must be inspected | Authenticate the sender and reconcile the event to a known user and product |

Before implementing a source, add a source-specific note recording:

- Official documentation or feed URL.
- Actual endpoint/feed URL and access method.
- Authentication requirements, if any.
- Pagination and rate-limit behavior.
- Terms or access restrictions relevant to collection.
- A sanitized example response fixture.
- Known gaps and parser limitations.

Do not put credentials or session material in this document or in fixtures.

## 6. FGC and ntfy event processing

FGC is an external claim-status reporter. Its event pipeline should:

1. Receive the event through the configured integration path.
2. Authenticate the sender independently of the ntfy topic name.
3. Validate the event shape and supported platform.
4. Resolve the event's product reference to a canonical `Product`.
5. Resolve the user from trusted server-side configuration or authenticated integration context. Never accept an arbitrary client-supplied `user_id` as proof of identity.
6. Deduplicate using a stable event identifier. If FGC does not provide one, define and test a deterministic fallback key.
7. Append a `ClaimEvent` with the original event time, received time, source, result, and sanitized evidence.
8. Update the current `Claim` projection only when the event represents a sufficiently reliable outcome.

Recommended mapping principles:

| FGC observation | Claim projection |
|---|---|
| Confirmed successful claim | `claimed` |
| Confirmed ownership already present | `claimed` |
| Failed attempt / login failure / CAPTCHA failure / timeout | Do not change current claim state |
| Ambiguous or unsupported result | `unknown` only when no reliable current state exists; otherwise preserve the last reliable state |

A failure event must remain visible in the event history even when it does not change the current claim projection.

The exact FGC event schema, ntfy topic configuration, and authentication mechanism must be inspected from the existing deployment before implementation. Do not assume the topic name is a credential.

## 7. Scheduling, retries, and failure isolation

Each source must fail independently. One unavailable storefront must not prevent other adapters from completing.

Recommended baseline behavior:

- Use explicit connection and read timeouts.
- Retry transient network failures and rate-limit responses with bounded exponential backoff and jitter.
- Respect server-provided retry guidance where applicable.
- Do not repeatedly retry permanent client errors or malformed payloads without a code/configuration change.
- Record the last successful fetch separately from the last attempted fetch.
- Avoid advancing a source cursor until the corresponding observations have been durably processed.
- Make ingestion idempotent so a repeated run does not create duplicate products, offers, or events.
- Use per-source scheduling or concurrency controls to prevent overlapping writes to the same JSON collection.
- Keep logs structured and redact credentials, tokens, cookies, and personal data.

A source failure should be recorded as an operational result. It must not be interpreted as evidence that all offers from that source have expired or disappeared.

## 8. Parser quality and test fixtures

Every parser should have sanitized fixtures covering at least:

- A normal valid response.
- An empty result.
- Missing optional fields.
- An unexpected or malformed field.
- A changed page/feed structure.
- Duplicate observations.
- A promotion with a known deadline.
- A promotion with an unknown deadline.
- An expired or unavailable promotion.
- A transient fetch failure and a permanent response failure.

Fixtures should not contain account credentials, session cookies, personal information, or other secrets.

Parser changes must be tested against the fixture set before deployment. Store the parser version with each fetch result so a changed interpretation can be traced.

## 9. Operational boundaries

- Storefront adapters and discovery adapters write catalog observations through the ingestion workflow.
- FGC events are processed by the claim integration and written through the Worker Claim Service defined in `API.md`.
- The browser must not write repository JSON directly.
- The browser must not receive a GitHub token.
- Public catalog data may be read publicly. User-specific claim data must follow the access policy defined by the API and CHIAuth contract.
- A public repository does not make credentials, private account data, or integration secrets safe to commit.

## 10. Decisions required before implementation

The following items remain explicitly open:

1. Verify the current official collection method and endpoint/feed for each storefront.
2. Inspect the existing 4Gamers RSS feed and define stable article identity.
3. Inspect the deployed FGC version and actual ntfy event payload.
4. Define the FGC sender authentication mechanism.
5. Decide raw-payload retention limits and whether payloads are stored in full or as bounded sanitized excerpts.
6. Define source-specific polling intervals and rate limits from verified platform behavior.
7. Define exact deterministic keys for offers and FGC events.
8. Confirm whether any source requires manual review before an offer can become `verified`.
9. Define the configuration format and allowlist for Generic adapter sources, including which feed types and reviewed page parsers are enabled.

These decisions should be resolved with evidence before writing production adapters. Until then, unknown details must remain marked as unknown rather than being filled with guessed endpoints or behavior.
