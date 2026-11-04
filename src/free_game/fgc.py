"""Read FGC claim notifications from the public ntfy topic."""

from __future__ import annotations

import json
import re
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
            external_id = FourGamersArticleAnalyzer._external_product_id(item_platform, parsed.path)
            if not external_id:
                external_id = parsed.path.rstrip("/").split("/")[-1]
            if not external_id:
                continue
            claims[(item_platform, external_id)] = {
                "platform": item_platform,
                "external_product_id": external_id,
                "title": title.strip(),
                "store_url": url,
            }
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
