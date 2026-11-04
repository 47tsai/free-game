"""Idempotent GitHub JSON catalog writer with SHA conflict retries."""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from free_game.adapters.base import NormalizedCandidate
from free_game.validation import validate_collection

_ID_NAMESPACE = uuid.UUID("a53b3d7c-cd0a-4d1e-96df-7d36e5e1d80f")


class ContentsConflictError(RuntimeError):
    """The target file changed since it was read."""


class ContentsStoreError(RuntimeError):
    """A GitHub Contents API operation failed."""


@dataclass(frozen=True, slots=True)
class StoredCollection:
    document: dict[str, Any]
    sha: str | None


class CollectionStore(Protocol):
    def read(self, path: str) -> StoredCollection:
        ...

    def write(self, path: str, document: dict[str, Any], sha: str | None) -> str:
        ...


class GitHubContentsStore:
    """Minimal GitHub Contents API store. The token is never included in errors."""

    def __init__(
        self,
        repository: str,
        token: str,
        *,
        branch: str = "main",
        timeout_seconds: float = 20.0,
    ) -> None:
        if "/" not in repository or not token:
            raise ValueError("repository owner/name and token are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.repository = repository
        self._token = token
        self.branch = branch
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None):
        url = (
            "https://api.github.com/repos/"
            + self.repository
            + "/contents/"
            + quote(path, safe="/")
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "FreeGameAggregator/0.1",
        }
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.status, response.read()
        except HTTPError as exc:
            return exc.code, exc.read()
        except URLError:
            raise ContentsStoreError("github_contents_network_error") from None

    def read(self, path: str) -> StoredCollection:
        status, body = self._request("GET", path)
        if status == 404:
            return StoredCollection(
                document={
                    "schema_version": 1,
                    "updated_at": _now(),
                    "records": [],
                },
                sha=None,
            )
        if status != 200:
            raise ContentsStoreError(f"github_contents_read_http_{status}")
        try:
            response = json.loads(body)
            encoded = response["content"].replace("\n", "")
            raw = base64.b64decode(encoded, validate=True)
            document = json.loads(raw.decode("utf-8"))
            sha = response["sha"]
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise ContentsStoreError("github_contents_response_invalid") from None
        if not isinstance(document, dict) or not isinstance(sha, str):
            raise ContentsStoreError("github_contents_document_invalid")
        return StoredCollection(document=document, sha=sha)

    def write(self, path: str, document: dict[str, Any], sha: str | None) -> str:
        raw = json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        payload: dict[str, Any] = {
            "message": f"Update {path}",
            "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha is not None:
            payload["sha"] = sha
        status, body = self._request("PUT", path, payload)
        if status == 409:
            raise ContentsConflictError("github_contents_sha_conflict")
        if status not in (200, 201):
            raise ContentsStoreError(f"github_contents_write_http_{status}")
        try:
            response = json.loads(body)
            result_sha = response["content"]["sha"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise ContentsStoreError("github_contents_write_response_invalid") from None
        if not isinstance(result_sha, str):
            raise ContentsStoreError("github_contents_write_sha_missing")
        return result_sha


@dataclass(frozen=True, slots=True)
class WriteResult:
    products_created: int
    products_updated: int
    source_records_created: int
    source_records_updated: int
    candidates_skipped: int
    commit_shas: tuple[str, ...]


class GitHubJsonWriter:
    """Persist product identities and provenance; never creates unverified offers."""

    PRODUCTS_PATH = "data/catalog/products.json"
    SOURCE_RECORDS_PATH = "data/catalog/source-records.json"

    def __init__(
        self,
        store: CollectionStore,
        *,
        max_conflict_retries: int = 3,
    ) -> None:
        if max_conflict_retries < 0:
            raise ValueError("max_conflict_retries cannot be negative")
        self.store = store
        self.max_conflict_retries = max_conflict_retries

    def write_candidates(
        self,
        candidates: tuple[NormalizedCandidate, ...] | list[NormalizedCandidate],
    ) -> WriteResult:
        now = _now()
        products_created = products_updated = 0
        sources_created = sources_updated = skipped = 0
        product_changes: dict[str, dict[str, Any]] = {}
        source_changes: dict[str, dict[str, Any]] = {}

        for candidate in candidates:
            if not self._is_persistable(candidate):
                skipped += 1
                continue
            assert candidate.source_external_id is not None
            source_id = _stable_id("source", candidate.source_key, candidate.source_external_id)
            product_id = None
            if candidate.platform and candidate.external_product_id and candidate.product_url:
                product_id = _stable_id(
                    "product", candidate.platform, candidate.external_product_id
                )

            source_payload = {
                "source": candidate.source_key,
                "external_id": candidate.source_external_id,
                "record_type": "store_product" if product_id else "discovery",
                "url": _https_url_or_none(candidate.product_url),
                "content_hash": _candidate_hash(candidate),
                "linked_entity_ids": [product_id] if product_id else [],
            }
            existing_source = source_changes.get(source_id)
            if existing_source is None:
                source_changes[source_id] = {
                    "id": source_id,
                    **source_payload,
                    "first_seen_at": _iso(candidate.observed_at),
                    "last_seen_at": _iso(candidate.observed_at),
                }
            else:
                existing_source["last_seen_at"] = max(
                    existing_source["last_seen_at"], _iso(candidate.observed_at)
                )
                existing_source["linked_entity_ids"] = sorted(
                    set(existing_source["linked_entity_ids"]) | set(source_payload["linked_entity_ids"])
                )

            if product_id is not None:
                product_payload = {
                    "id": product_id,
                    "game_id": None,
                    "platform": candidate.platform,
                    "external_product_id": candidate.external_product_id,
                    "title": candidate.title.strip(),
                    "product_url": candidate.product_url,
                    "created_at": _iso(candidate.observed_at),
                    "updated_at": now,
                    "source_record_ids": [source_id],
                }
                existing_product = product_changes.get(product_id)
                if existing_product is None:
                    product_changes[product_id] = product_payload
                else:
                    existing_product["source_record_ids"] = sorted(
                        set(existing_product["source_record_ids"]) | {source_id}
                    )
                    if _iso(candidate.observed_at) >= existing_product["updated_at"]:
                        existing_product["title"] = candidate.title.strip()
                        existing_product["product_url"] = candidate.product_url
                        existing_product["updated_at"] = now

        if not source_changes:
            return WriteResult(0, 0, 0, 0, skipped, ())

        source_stats, source_sha = self._upsert(
            self.SOURCE_RECORDS_PATH, source_changes, _merge_source_record
        )
        product_stats = (0, 0)
        product_sha = None
        if product_changes:
            product_stats, product_sha = self._upsert(
                self.PRODUCTS_PATH, product_changes, _merge_product
            )

        commits = tuple(sha for sha in (source_sha, product_sha) if sha is not None)
        return WriteResult(
            products_created=product_stats[0],
            products_updated=product_stats[1],
            source_records_created=source_stats[0],
            source_records_updated=source_stats[1],
            candidates_skipped=skipped,
            commit_shas=commits,
        )

    def _upsert(
        self,
        path: str,
        changes: dict[str, dict[str, Any]],
        merge: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    ) -> tuple[tuple[int, int], str | None]:
        for attempt in range(self.max_conflict_retries + 1):
            stored = self.store.read(path)
            document = dict(stored.document)
            records = document.get("records")
            if not isinstance(records, list):
                raise ContentsStoreError(f"{path}:records_must_be_array")
            by_id: dict[str, dict[str, Any]] = {}
            for record in records:
                if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                    raise ContentsStoreError(f"{path}:existing_record_invalid")
                if record["id"] in by_id:
                    raise ContentsStoreError(f"{path}:duplicate_existing_id")
                by_id[record["id"]] = record

            created = updated = 0
            for record_id, incoming in changes.items():
                if record_id in by_id:
                    by_id[record_id] = merge(by_id[record_id], incoming)
                    updated += 1
                else:
                    by_id[record_id] = incoming
                    created += 1

            document["schema_version"] = 1
            document["updated_at"] = _now()
            document["records"] = sorted(by_id.values(), key=lambda item: item["id"])
            validate_collection(document)
            try:
                sha = self.store.write(path, document, stored.sha)
                return (created, updated), sha
            except ContentsConflictError:
                if attempt >= self.max_conflict_retries:
                    raise
                time.sleep(min(0.1 * (2 ** attempt), 1.0))
        raise ContentsConflictError("github_contents_conflict_retries_exhausted")

    @staticmethod
    def _is_persistable(candidate: NormalizedCandidate) -> bool:
        if candidate.verification_status != "candidate":
            return False
        if not candidate.source_key.strip() or not candidate.title.strip():
            return False
        if not candidate.source_external_id or not candidate.source_external_id.strip():
            return False
        if candidate.platform is None or candidate.external_product_id is None:
            return True
        if not candidate.platform.strip() or not candidate.external_product_id.strip():
            return False
        if candidate.product_url is None:
            return False
        from urllib.parse import urlparse

        parsed = urlparse(candidate.product_url)
        return parsed.scheme == "https" and bool(parsed.netloc)


def _stable_id(kind: str, *parts: str) -> str:
    return f"{kind}_{uuid.uuid5(_ID_NAMESPACE, chr(31).join((kind, *parts)))}"


def _candidate_hash(candidate: NormalizedCandidate) -> str:
    content = json.dumps(
        {
            "platform": candidate.platform,
            "external_product_id": candidate.external_product_id,
            "title": candidate.title.strip(),
            "product_url": candidate.product_url,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("candidate timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _merge_source_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["last_seen_at"] = max(existing["last_seen_at"], incoming["last_seen_at"])
    merged["linked_entity_ids"] = sorted(
        set(existing.get("linked_entity_ids", [])) | set(incoming.get("linked_entity_ids", []))
    )
    if incoming.get("url"):
        merged["url"] = incoming["url"]
    if incoming.get("content_hash"):
        merged["content_hash"] = incoming["content_hash"]
    return merged


def _merge_product(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["source_record_ids"] = sorted(
        set(existing.get("source_record_ids", [])) | set(incoming["source_record_ids"])
    )
    if incoming["updated_at"] >= existing["updated_at"]:
        merged["title"] = incoming["title"]
        merged["product_url"] = incoming["product_url"]
        merged["updated_at"] = incoming["updated_at"]
    return merged



def _https_url_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.netloc else None
