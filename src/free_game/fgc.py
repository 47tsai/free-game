"""Read FGC claim notifications from the public ntfy topic."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from free_game.article_analysis import FourGamersArticleAnalyzer

_TOPIC_URL = "https://ntfy.sh/47tsai-fgc/json?poll=1&since=24h"
_HEADER = re.compile(r"^\s*\*\*([^*]+)\*\*\s*\([^)]*\):\s*$")
_ITEM = re.compile(r"^\s*[•*\-]\s*\*\*\[([^]]+)\]\((https://[^)]+)\)\*\*\s*:\s*(claimed)\s*$", re.I)
_PLATFORM_HOSTS = {
    "steam": "steam", "epic": "epic", "epic games": "epic", "epic games store": "epic",
    "gog": "gog", "ubisoft": "ubisoft", "dlsite": "dlsite",
}
# Path segments that are not a product identity: locale prefixes such as
# "/en" and storefront roots such as "/game". Using one as an
# external_product_id (e.g. GOG's "https://www.gog.com/en" -> "en") makes
# the claim match nothing and creates a duplicate record.
_GENERIC_PATH_SEGMENTS = {
    "en", "zh", "zh-tw", "zh-cn", "zh-hk", "ja", "ko", "de", "fr", "es",
    "pt", "ru", "pl", "game", "games", "store", "p", "app", "products",
    "product", "catalog", "search",
}
_LOCALE_SEGMENT = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$")


def _external_product_id_or_none(platform: str, path: str) -> str | None:
    external_id = FourGamersArticleAnalyzer._external_product_id(platform, path)
    if external_id:
        return external_id
    segment = path.rstrip("/").split("/")[-1] if path.rstrip("/") else ""
    if not segment:
        return None
    if segment.casefold() in _GENERIC_PATH_SEGMENTS or _LOCALE_SEGMENT.match(segment):
        return None
    return segment


class FGCError(RuntimeError):
    pass


def parse_fgc_messages(payload: str | bytes) -> list[dict]:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    claims: dict[tuple[str, str], dict] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        if not isinstance(message, str):
            continue
        platform = None
        for item_line in message.splitlines():
            header = _HEADER.match(item_line)
            if header:
                platform = _PLATFORM_HOSTS.get(header.group(1).strip().casefold())
                continue
            item = _ITEM.match(item_line)
            if not item:
                continue
            title, url, _ = item.groups()
            parsed = urlparse(url)
            item_platform = platform or (parsed.hostname or "").lower().removeprefix("www.")
            if not item_platform:
                continue
            title = title.strip()
            if not title:
                continue
            # A link without a product slug (e.g. GOG "https://www.gog.com/en")
            # has no usable external id. Keep the claim, keyed by title, so
            # the writer can match it against the catalog instead of
            # inventing an id such as "en" and creating a duplicate record.
            # The ntfy event time is the claim time; the writer uses it as
            # the anchor for the time-window fallback when the title does
            # not match either.
            external_id = _external_product_id_or_none(item_platform, parsed.path)
            key = (item_platform, external_id) if external_id else (item_platform, "title:" + title.casefold())
            if key in claims:
                continue
            claim: dict = {
                "platform": item_platform,
                "external_product_id": external_id,
                "title": title,
                "store_url": url,
            }
            event_time = event.get("time")
            if isinstance(event_time, (int, float)) and event_time > 0:
                claim["claimed_at"] = datetime.fromtimestamp(event_time, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            claims[key] = claim
    return list(claims.values())


def fetch_fgc_claims(*, timeout_seconds: float = 20.0) -> list[dict]:
    request = Request(_TOPIC_URL, headers={"Accept": "application/x-ndjson", "User-Agent": "FreeGameAggregator/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(2_000_001)
    except HTTPError as exc:
        raise FGCError(f"ntfy_http_{exc.code}") from None
    except URLError:
        raise FGCError("ntfy_network_error") from None
    if len(payload) > 2_000_000:
        raise FGCError("ntfy_response_too_large")
    return parse_fgc_messages(payload)
