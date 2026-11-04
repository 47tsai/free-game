"""GitHub JSON persistence for the unified game catalog."""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from free_game.adapters.base import NormalizedCandidate
from free_game.validation import validate_collection

_ID_NAMESPACE = uuid.UUID("a53b3d7c-cd0a-4d1e-96df-7d36e5e1d80f")


class ContentsConflictError(RuntimeError):
    pass


class ContentsStoreError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredCollection:
    document: dict[str, Any]
    sha: str | None


class CollectionStore(Protocol):
    def read(self, path: str) -> StoredCollection: ...
    def write(self, path: str, document: dict[str, Any], sha: str | None) -> str: ...


class GitHubContentsStore:
    """Minimal GitHub Contents API client. Never exposes its token in errors."""

    def __init__(self, repository: str, token: str, *, branch: str = "main", timeout_seconds: float = 20.0) -> None:
        if "/" not in repository or not token:
            raise ValueError("repository owner/name and token are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.repository = repository
        self._token = token
        self.branch = branch
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None):
        url = "https://api.github.com/repos/" + self.repository + "/contents/" + quote(path, safe="/")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self._token,
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
            return StoredCollection({"schema_version": 1, "updated_at": _now(), "records": []}, None)
        if status != 200:
            raise ContentsStoreError("github_contents_read_http_" + str(status))
        try:
            response = json.loads(body)
            raw = base64.b64decode(response["content"].replace("\n", ""), validate=True)
            document = json.loads(raw.decode("utf-8"))
            sha = response["sha"]
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise ContentsStoreError("github_contents_response_invalid") from None
        if not isinstance(document, dict) or not isinstance(sha, str):
            raise ContentsStoreError("github_contents_document_invalid")
        return StoredCollection(document, sha)

    def write(self, path: str, document: dict[str, Any], sha: str | None) -> str:
        raw = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        payload = {
            "message": "Update " + path,
            "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        status, body = self._request("PUT", path, payload)
        if status == 409:
            raise ContentsConflictError("github_contents_sha_conflict")
        if status not in (200, 201):
            raise ContentsStoreError("github_contents_write_http_" + str(status))
        try:
            result_sha = json.loads(body)["content"]["sha"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise ContentsStoreError("github_contents_write_response_invalid") from None
        if not isinstance(result_sha, str):
            raise ContentsStoreError("github_contents_write_sha_missing")
        return result_sha


@dataclass(frozen=True, slots=True)
class WriteResult:
    games_created: int
    games_updated: int
    candidates_skipped: int
    commit_sha: str | None


@dataclass(frozen=True, slots=True)
class NotificationWriteResult:
    created: int
    updated: int
    commit_sha: str | None


class GitHubJsonWriter:
    GAMES_PATH = "data/catalog/games.json"
    NOTIFICATIONS_PATH = "data/operations/notifications.json"

    def __init__(self, store: CollectionStore, *, max_conflict_retries: int = 3) -> None:
        if max_conflict_retries < 0:
            raise ValueError("max_conflict_retries cannot be negative")
        self.store = store
        self.max_conflict_retries = max_conflict_retries

    def write_candidates(self, candidates: tuple[NormalizedCandidate, ...] | list[NormalizedCandidate]) -> WriteResult:
        stored = self.store.read(self.GAMES_PATH)
        records = stored.document.get("records")
        if not isinstance(records, list):
            raise ContentsStoreError("games:records_must_be_array")
        existing = {item["id"]: item for item in records if isinstance(item, dict) and isinstance(item.get("id"), str)}
        changes: dict[str, dict[str, Any]] = {}
        skipped = 0
        for candidate in candidates:
            if not self._is_persistable(candidate):
                skipped += 1
                continue
            if candidate.platform and candidate.external_product_id:
                game_id = _stable_id("game", candidate.platform, candidate.external_product_id)
            else:
                game_id = _stable_id("game", candidate.source_key, candidate.source_external_id or "")
            previous = changes.get(game_id) or existing.get(game_id, {})
            now = _now()
            article_url = candidate.article_url or (candidate.product_url if not candidate.platform else None)
            store_url = candidate.product_url if candidate.platform else previous.get("store_url")
            incoming = {
                "id": game_id,
                "title": candidate.title.strip(),
                "normalized_title": _normalize_title(candidate.title),
                "platform": candidate.platform or previous.get("platform"),
                "external_product_id": candidate.external_product_id or previous.get("external_product_id"),
                "store_url": _https_url_or_none(store_url),
                "article_url": _https_url_or_none(article_url) or previous.get("article_url"),
                "cover_image_url": _https_url_or_none(candidate.image_url) or previous.get("cover_image_url"),
                "claim_status": previous.get("claim_status", "unclaimed"),
                "claimed_at": previous.get("claimed_at"),
                "claim_source": previous.get("claim_source"),
                "claim_notification_pending": previous.get("claim_notification_pending", False),
                "added_at": previous.get("added_at") if previous.get("article_url") else now,
                "reminder_last_sent_at": previous.get("reminder_last_sent_at"),
                "created_at": previous.get("created_at", now),
                "updated_at": now,
            }
            merged = _merge_game(previous, incoming)
            if previous and all(previous.get(key) == value for key, value in merged.items() if key != "updated_at"):
                continue
            changes[game_id] = merged
        if not changes:
            return WriteResult(0, 0, skipped, None)
        (created, updated), sha = self._upsert(self.GAMES_PATH, changes, _merge_game)
        return WriteResult(created, updated, skipped, sha)

    def sync_fgc_claims(self, claims: list[dict]) -> tuple[tuple[int, int], str | None]:
        now = _now()
        stored = self.store.read(self.GAMES_PATH)
        records = stored.document.get("records")
        if not isinstance(records, list):
            raise ContentsStoreError("games:records_must_be_array")
        existing = {item["id"]: item for item in records if isinstance(item, dict) and isinstance(item.get("id"), str)}
        changes: dict[str, dict[str, Any]] = {}
        for claim in claims:
            platform, external_id, title, store_url = (claim.get(key) for key in ("platform", "external_product_id", "title", "store_url"))
            if not all(isinstance(value, str) and value.strip() for value in (platform, external_id, title)):
                continue
            game_id = _stable_id("game", platform, external_id)
            previous = changes.get(game_id) or existing.get(game_id, {})
            incoming = {
                "id": game_id,
                "title": previous.get("title") or title.strip(),
                "normalized_title": previous.get("normalized_title") or _normalize_title(title),
                "platform": platform,
                "external_product_id": external_id,
                "store_url": previous.get("store_url") or _https_url_or_none(store_url),
                "article_url": previous.get("article_url"),
                "cover_image_url": previous.get("cover_image_url"),
                "claim_status": "claimed",
                "claimed_at": previous.get("claimed_at") or now,
                "claim_source": previous.get("claim_source") or "fgc",
                "claim_notification_pending": previous.get("claim_notification_pending", False) or previous.get("claim_status") != "claimed",
                "added_at": previous.get("added_at") or now,
                "reminder_last_sent_at": previous.get("reminder_last_sent_at"),
                "created_at": previous.get("created_at", now),
                "updated_at": now,
            }
            changes[game_id] = _merge_game(previous, incoming)
        if not changes:
            return (0, 0), None
        return self._upsert(self.GAMES_PATH, changes, _merge_game)

    def update_game(self, game_id: str, changes: dict[str, Any]) -> None:
        records = self.store.read(self.GAMES_PATH).document.get("records", [])
        existing = next((item for item in records if isinstance(item, dict) and item.get("id") == game_id), None)
        if existing is None:
            raise ContentsStoreError("game_not_found")
        merged = dict(existing)
        merged.update(changes)
        merged["updated_at"] = _now()
        self._upsert(self.GAMES_PATH, {game_id: merged}, _merge_game)

    def write_notification(self, notification: dict[str, Any]) -> NotificationWriteResult:
        if not isinstance(notification, dict) or not isinstance(notification.get("id"), str):
            raise ValueError("notification must contain a stable id")
        (created, updated), sha = self._upsert(
            self.NOTIFICATIONS_PATH,
            {notification["id"]: notification},
            _merge_notification,
        )
        return NotificationWriteResult(created, updated, sha)

    def _upsert(self, path: str, changes: dict[str, dict[str, Any]], merge):
        for attempt in range(self.max_conflict_retries + 1):
            stored = self.store.read(path)
            document = dict(stored.document)
            records = document.get("records")
            if not isinstance(records, list):
                raise ContentsStoreError(path + ":records_must_be_array")
            by_id = {}
            for item in records:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    raise ContentsStoreError(path + ":existing_record_invalid")
                if item["id"] in by_id:
                    raise ContentsStoreError(path + ":duplicate_existing_id")
                by_id[item["id"]] = item
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
                return (created, updated), self.store.write(path, document, stored.sha)
            except ContentsConflictError:
                if attempt >= self.max_conflict_retries:
                    raise
                time.sleep(min(0.1 * (2 ** attempt), 1.0))
        raise ContentsConflictError("github_contents_conflict_retries_exhausted")

    @staticmethod
    def _is_persistable(candidate: NormalizedCandidate) -> bool:
        if not candidate.source_key.strip() or not candidate.title.strip() or not candidate.source_external_id:
            return False
        if candidate.platform and candidate.external_product_id:
            return bool(_https_url_or_none(candidate.product_url))
        return bool(_https_url_or_none(candidate.article_url or candidate.product_url))


def _merge_game(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"claim_status", "claimed_at", "claim_source"} and existing.get("claim_status") == "claimed":
            if value in (None, "unclaimed"):
                continue
        if key == "added_at" and existing.get("article_url"):
            continue
        merged[key] = value
    return merged


def _merge_notification(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    # A confirmed delivery is terminal; pending/failed records must accept
    # the delivery result written by the notification processor.
    if existing.get("status") == "sent":
        return merged
    merged.update(incoming)
    merged["attempt_count"] = max(
        int(existing.get("attempt_count", 0)),
        int(incoming.get("attempt_count", 0)),
    )
    return merged


def _stable_id(kind: str, *parts: str) -> str:
    return kind + "_" + str(uuid.uuid5(_ID_NAMESPACE, chr(31).join((kind, *parts))))


def _normalize_title(value: str) -> str:
    import unicodedata
    normalized = unicodedata.normalize("NFKC", value).casefold()
    output = []
    previous_space = True
    for character in normalized:
        if unicodedata.category(character)[0] in {"L", "N"}:
            output.append(character)
            previous_space = False
        elif not previous_space:
            output.append(" ")
            previous_space = True
    return "".join(output).strip()


def _https_url_or_none(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.netloc else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
