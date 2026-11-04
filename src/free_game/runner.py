"""Small bounded HTTP fetcher for 4Gamers RSS and article pages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class HTTPFetchResponse:
    body: bytes
    status_code: int
    final_url: str


class SourceFetchError(RuntimeError):
    pass


class HTTPFetcher:
    def __init__(self, *, timeout_seconds: float = 20.0, max_response_bytes: int = 5_000_000) -> None:
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("fetch limits must be positive")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def fetch(self, url: str) -> HTTPFetchResponse:
        if urlparse(url).scheme != "https" or not urlparse(url).netloc:
            raise SourceFetchError("source_url_must_be_absolute_https")
        request = Request(url, headers={
            "User-Agent": "FreeGameAggregator/0.1 (+https://github.com/47tsai/free-game)",
            "Accept": "application/rss+xml, application/xml, text/xml, text/html",
        })
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                final_url = response.geturl()
                if urlparse(final_url).scheme != "https":
                    raise SourceFetchError("redirected_to_non_https_url")
                body = response.read(self.max_response_bytes + 1)
                status = getattr(response, "status", 200)
        except HTTPError as exc:
            raise SourceFetchError("http_status_" + str(exc.code)) from None
        except URLError:
            raise SourceFetchError("network_error") from None
        if len(body) > self.max_response_bytes:
            raise SourceFetchError("response_too_large")
        if status < 200 or status >= 300:
            raise SourceFetchError("http_status_" + str(status))
        return HTTPFetchResponse(body, status, final_url)
