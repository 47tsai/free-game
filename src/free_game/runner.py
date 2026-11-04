"""HTTP source fetching and isolated per-source ingestion runner."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
from typing import Protocol

from free_game.adapters.base import FetchResult
from free_game.ingestion import IngestionPipeline, IngestionResult
from free_game.registry import SourceRegistry


@dataclass(frozen=True, slots=True)
class HTTPFetchResponse:
    body: bytes
    status_code: int
    final_url: str


class Fetcher(Protocol):
    def fetch(self, url: str) -> HTTPFetchResponse:
        """Fetch one configured source URL."""


class SourceFetchError(RuntimeError):
    """A safe, non-secret-bearing source fetch failure."""


class HTTPFetcher:
    """Small standard-library HTTP client with bounded time and response size."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 5_000_000,
        user_agent: str = "FreeGameAggregator/0.1 (+https://github.com/47tsai/free-game)",
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.user_agent = user_agent

    def fetch(self, url: str) -> HTTPFetchResponse:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise SourceFetchError("source_url_must_be_absolute_https")

        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, application/atom+xml, application/rss+xml, application/xml, text/xml",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                final_url = response.geturl()
                if urlparse(final_url).scheme != "https":
                    raise SourceFetchError("redirected_to_non_https_url")
                body = response.read(self.max_response_bytes + 1)
                status_code = getattr(response, "status", 200)
        except HTTPError as exc:
            raise SourceFetchError(f"http_status_{exc.code}") from None
        except URLError:
            raise SourceFetchError("network_error") from None

        if len(body) > self.max_response_bytes:
            raise SourceFetchError("response_too_large")
        if status_code < 200 or status_code >= 300:
            raise SourceFetchError(f"http_status_{status_code}")
        return HTTPFetchResponse(
            body=body,
            status_code=status_code,
            final_url=final_url,
        )


@dataclass(frozen=True, slots=True)
class SourceRunResult:
    source_key: str
    fetch_result: FetchResult | None
    ingestion_result: IngestionResult | None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.ingestion_result is not None


class SourceRunner:
    """Fetch and ingest configured sources independently; does not persist."""

    def __init__(
        self,
        registry: SourceRegistry,
        *,
        fetcher: Fetcher | None = None,
        pipeline: IngestionPipeline | None = None,
    ) -> None:
        self.registry = registry
        self.fetcher = fetcher or HTTPFetcher()
        self.pipeline = pipeline or IngestionPipeline()

    def run_all(self) -> tuple[SourceRunResult, ...]:
        definitions = {
            definition.source_key: definition
            for definition in self.registry.definitions
            if definition.enabled
        }
        adapters = self.registry.build_enabled()
        results: list[SourceRunResult] = []

        for adapter in adapters:
            definition = definitions[adapter.source_key]
            fetch_result: FetchResult | None = None
            try:
                response = self.fetcher.fetch(definition.source_url)
                fetched_at = datetime.now(timezone.utc)
                fetch_result = FetchResult(
                    source_key=adapter.source_key,
                    fetched_at=fetched_at,
                    request_url=self._redact_url(definition.source_url),
                    http_status=response.status_code,
                    payload_hash=hashlib.sha256(response.body).hexdigest(),
                )
                ingestion_result = self.pipeline.run(adapter, response.body)
                results.append(SourceRunResult(
                    source_key=adapter.source_key,
                    fetch_result=fetch_result,
                    ingestion_result=ingestion_result,
                ))
            except Exception as exc:
                # Do not include exception text: HTTP/client errors may contain
                # signed URLs, query tokens, or other source credentials.
                error = f"{type(exc).__name__}:source_processing_failed"
                results.append(SourceRunResult(
                    source_key=adapter.source_key,
                    fetch_result=fetch_result,
                    ingestion_result=None,
                    error=error,
                ))
        return tuple(results)

    @staticmethod
    def _redact_url(url: str) -> str:
        parsed = urlparse(url)
        sensitive = ("token", "key", "auth", "password", "secret", "signature", "sig")
        query = [
            (name, "[REDACTED]" if any(part in name.lower() for part in sensitive) else value)
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        return urlunparse(parsed._replace(query=urlencode(query)))
