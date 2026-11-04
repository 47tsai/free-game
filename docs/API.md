# Free Game API Specification

This document defines the initial API contract for the Cloudflare Worker. It complements [ARCHITECTURE.md](./ARCHITECTURE.md) and [DATA_MODEL.md](./DATA_MODEL.md).

## 1. API responsibilities

The Worker is the trusted API boundary between the browser, CHIAuth, and GitHub-backed JSON data.

It is responsible for:
- Serving public catalog data where useful.
- Verifying CHIAuth authentication for protected operations.
- Enforcing user ownership on claim reads and writes.
- Accepting authenticated FGC event ingestion from a trusted server-side caller.
- Reading and writing the relevant GitHub JSON files using server-side credentials.
- Applying validation, idempotency, and conflict handling.

The Worker is not a general-purpose database and must not expose GitHub credentials to the browser.

Base path: `/api/v1`.

All request and response bodies use UTF-8 JSON. All timestamps are ISO-8601 UTC strings.

## 2. Authentication and authorization

### Browser user authentication

Protected browser requests must include the CHIAuth-issued credential using the agreed CHIAuth integration mechanism. The Worker must validate the credential's signature, issuer, audience, expiry, and required claims according to the CHIAuth contract.

The authenticated subject (`sub`) is the canonical `user_id`.

Rules:
- Never trust a client-supplied `user_id` for authorization.
- A user may read or modify only their own private-to-account view and claim mutations.
- Public visibility of claim records does not grant write permission.
- Reject missing, invalid, expired, or wrong-audience credentials.
- Do not log bearer tokens, cookies, authorization headers, or secrets.

The exact CHIAuth token format, issuer, audience, JWKS/key retrieval, and callback details must be confirmed against the existing CHIAuth service before implementation. Do not guess these values.

### FGC server authentication

FGC event ingestion must use a separate server-to-server credential stored as a Worker secret and on the trusted sender. Do not treat possession of a public ntfy topic name as authentication.

The Worker must validate the sender credential, validate the event shape, deduplicate upstream event IDs where available, and map the event to a known user and platform Product. The mapping between the current FGC instance and CHIAuth user must be configured server-side, not supplied freely by the event body.

## 3. Endpoint overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/health` | Public | Basic service health |
| GET | `/api/v1/games` | Public | Browse games |
| GET | `/api/v1/products` | Public | Browse platform products |
| GET | `/api/v1/offers` | Public | Browse offers |
| GET | `/api/v1/offers/{offer_id}` | Public | Offer detail |
| GET | `/api/v1/me` | CHIAuth | Current authenticated identity |
| GET | `/api/v1/me/claims` | CHIAuth | Current user's claims |
| PUT | `/api/v1/me/claims/{product_id}` | CHIAuth | Set current user's claim state |
| POST | `/api/v1/integrations/fgc/events` | Server credential | Ingest FGC event |
| GET | `/api/v1/me/claims/export` | CHIAuth | Export current user's claim records |

Public endpoints must return only fields intended for public display. They must never return credentials, internal operational state, private integration configuration, or raw untrusted payloads.

## 4. Request and response contracts

### 4.1 Health

`GET /api/v1/health`

Example response:

```json
{
  "status": "ok",
  "service": "free-game-api",
  "api_version": 1
}
```

This endpoint confirms that the Worker is responding. It must not expose secret configuration or private dependency details.

### 4.2 Public catalog

`GET /api/v1/games`

`GET /api/v1/products`

`GET /api/v1/offers`

Supported query parameters should be consistent:
- `limit`: bounded page size with a conservative default and maximum.
- `cursor`: opaque pagination cursor.
- `platform`: canonical platform key.
- `status`: supported offer status filter.
- `q`: bounded search string.

Example response:

```json
{
  "data": [],
  "page": {
    "next_cursor": null,
    "has_more": false
  }
}
```

Do not promise arbitrary full-text search until the static JSON/index strategy is implemented and measured. Reject invalid filters and excessive limits.

### 4.3 Current identity

`GET /api/v1/me`

Requires CHIAuth authentication.

Example response:

```json
{
  "user": {
    "id": "chi-auth-subject",
    "display_name": null
  }
}
```

Return only identity fields explicitly approved for frontend display.

### 4.4 List claims

`GET /api/v1/me/claims`

Requires CHIAuth authentication. The user identity is derived from the verified credential.

Optional filters:
- `platform`
- `status`
- `cursor`
- `limit`

Example response:

```json
{
  "data": [],
  "page": {
    "next_cursor": null,
    "has_more": false
  }
}
```

The initial product decision allows claim records to be publicly readable in the repository. The authenticated endpoint nevertheless returns only the current user's records by default. A separate public aggregate or public claims endpoint would require an explicit contract and privacy review.

### 4.5 Set claim state

`PUT /api/v1/me/claims/{product_id}`

Requires CHIAuth authentication.

Request:

```json
{
  "status": "claimed"
}
```

Allowed status values: `claimed`, `unclaimed`, `unknown`.

The server:
1. Validates the CHIAuth credential.
2. Derives `user_id` from the verified subject.
3. Validates the Product exists.
4. Applies the state transition and records a ClaimEvent.
5. Persists the claim using the single claim writer.
6. Returns the resulting current Claim.

The client cannot set `user_id`, `source`, `claimed_at`, or internal event IDs. For a manual update, the server sets `source=manual` and manages timestamps. If status is changed to `unclaimed` or `unknown`, clear `claimed_at` unless a separate historical claim event preserves the prior claim.

Example response:

```json
{
  "data": {
    "id": "claim-id",
    "product_id": "product-id",
    "status": "claimed",
    "source": "manual",
    "claimed_at": "2026-11-04T12:00:00Z",
    "updated_at": "2026-11-04T12:00:00Z"
  }
}
```

### 4.6 FGC event ingestion

`POST /api/v1/integrations/fgc/events`

Requires the dedicated server-to-server credential.

The exact request mapping must be based on real FGC/ntfy payload samples before implementation. The normalized internal event should include:
- stable upstream event ID when available;
- configured user mapping;
- platform key;
- platform external product identifier;
- success/failure event type;
- event timestamp;
- sanitized diagnostic details.

Processing rules:
- Duplicate upstream events are acknowledged without creating duplicate ClaimEvents.
- Successful claims update the Claim to `claimed`.
- Failed attempts create a ClaimEvent but do not automatically set the Claim to `unclaimed` or `failed`.
- A stale event must not overwrite a newer manual state without an explicit conflict policy.
- Unknown product mappings are recorded for review and must not be guessed from a title alone.

Example acknowledgement:

```json
{
  "accepted": true,
  "duplicate": false
}
```

### 4.7 Claim export

`GET /api/v1/me/claims/export`

Requires CHIAuth authentication. Returns only the current user's claim records in a documented JSON format. This is intended for portability and recovery, not as a write interface.

## 5. Error format

Use a consistent error response:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Authentication is required."
  }
}
```

Suggested HTTP status mapping:
- `400`: invalid request or unsupported filter.
- `401`: missing or invalid authentication.
- `403`: authenticated but not authorized.
- `404`: resource not found.
- `409`: version conflict or incompatible state transition.
- `422`: structurally valid request with invalid domain data.
- `429`: rate limit exceeded.
- `500`: unexpected internal error.
- `503`: required upstream storage service unavailable.

Do not return stack traces, GitHub API tokens, raw authorization data, or unfiltered upstream error bodies.

## 6. GitHub JSON write ownership

GitHub JSON files do not provide transactions or row-level locking. To avoid lost updates, each mutable dataset must have one logical writer.

Initial ownership proposal:
- Catalog files (games/products/offers/source records): Python ingestion workflow.
- Notification and scheduler state: the relevant scheduled workflow.
- Claim and ClaimEvent files: Worker Claim service only.
- FGC events: Worker receives and applies them through the same Claim service.
- Website manual changes: Worker applies them through the same Claim service.

Actions must not independently edit claim files. If the Python FGC consumer remains responsible for reading ntfy, it should forward normalized events to the authenticated Worker ingestion endpoint rather than committing claim JSON itself.

Worker writes must:
1. Fetch the latest file and blob SHA.
2. Apply an idempotent mutation.
3. Write with the expected SHA.
4. On conflict, reread and reapply with bounded retries.
5. Return a retryable error if the conflict cannot be resolved.

If GitHub API rate limits or concurrent writes become problematic, reassess the storage layer rather than silently introducing a second persistence system.

## 7. CORS, rate limits, and input safety

- Allow only the production GitHub Pages origin and explicitly configured development origins.
- Do not use wildcard CORS with credentials.
- Validate HTTP method, content type, body size, path parameters, query parameters, and JSON schema.
- Apply rate limits to authentication-sensitive and write endpoints.
- Use idempotency keys for event ingestion and any retryable mutation.
- Treat all source-provided titles, descriptions, URLs, and metadata as untrusted content.
- Render source text safely; never inject source HTML directly into the page.
- Restrict outbound fetches to expected GitHub API hosts and configured upstream endpoints to avoid SSRF.
- Store GitHub tokens, CHIAuth secrets, and FGC integration credentials only as Worker/Actions secrets.

## 8. Implementation gates

Do not implement the API until these inputs are confirmed:
1. Existing CHIAuth token contract: issuer, audience, signing algorithm, key discovery, and callback behavior.
2. Existing Worker deployment and secret configuration.
3. Actual FGC/ntfy event samples, including success and failure cases.
4. GitHub repository permissions and token scope needed for Worker writes.
5. Production Pages origin and any custom domain.

The API contract may be refined after inspecting the existing CHIAuth and FGC integrations. Do not invent compatibility details.
