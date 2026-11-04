"""Extract storefront game candidates from 4Gamers article pages."""

from __future__ import annotations

import hashlib
import re
from html import unescape
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, urlunparse

from free_game.adapters.base import NormalizedCandidate, SourceObservation


_IGNORED_HOSTS = {
    "4gamers.com.tw", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "youtube.com", "youtu.be", "discord.gg", "discord.com",
    "line.me", "twitch.tv", "google.com", "apple.com",
}
_STORE_HOSTS = {
    "store.steampowered.com": "steam",
    "store.epicgames.com": "epic",
    "gog.com": "gog",
    "store.ubi.com": "ubisoft",
    "store.ubisoft.com": "ubisoft",
    "dlsite.com": "dlsite",
}
_GENERIC_LABELS = {
    "steam", "steam 商店", "epic games store", "epic games", "gog", "gog.com",
    "ubisoft", "ubisoft store", "dlsite", "立即領取", "前往商店",
    "商店連結", "點此前往", "點此領取",
}
_STORE_SUFFIX_RE = re.compile(
    r"\s*(?:[｜|]|[-（(])\s*(?:steam(?: 商店)?|epic games store|epic games|"
    r"gog(?:\.com)?|ubisoft(?: store)?|dlsite)\s*[）)]?\s*$",
    re.IGNORECASE,
)


class _ArticleHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.in_body = False
        self.skip_depth = 0
        self.links: list[tuple[str, str]] = []
        self.body_text: list[str] = []
        self.image_url: str | None = None
        self._active_url: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_map = dict(attrs)
        if tag == "body":
            self.in_body = True
        if tag == "meta":
            prop = (attrs_map.get("property") or attrs_map.get("name") or "").lower()
            if prop in {"og:image", "twitter:image"} and attrs_map.get("content"):
                candidate = urljoin(self.base_url, unescape(attrs_map["content"]))
                if urlparse(candidate).scheme == "https":
                    self.image_url = candidate
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if tag == "a" and attrs_map.get("href"):
            absolute = urljoin(self.base_url, unescape(attrs_map["href"]))
            parsed = urlparse(absolute)
            host = (parsed.hostname or "").lower().rstrip(".")
            article_host = (urlparse(self.base_url).hostname or "").lower().rstrip(".")
            ignored = any(host == domain or host.endswith("." + domain) for domain in _IGNORED_HOSTS)
            same_site = host == article_host or host.endswith("." + article_host)
            if parsed.scheme == "https" and host and not ignored and not same_site:
                self._active_url = urlunparse(parsed._replace(query="", fragment=""))
                self._active_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "a" and self._active_url:
            label = " ".join(" ".join(self._active_text).split())
            self.links.append((self._active_url, label))
            self._active_url = None
            self._active_text = []
        if tag == "body":
            self.in_body = False

    def handle_data(self, data: str) -> None:
        if self.in_body and not self.skip_depth:
            value = " ".join(data.split())
            if value:
                self.body_text.append(value)
                if self._active_url:
                    self._active_text.append(value)

    @staticmethod
    def _platform(host: str) -> str | None:
        for domain, platform in _STORE_HOSTS.items():
            if host == domain or host.endswith("." + domain):
                return platform
        return None


class FourGamersArticleAnalyzer:
    """Fetch-independent article parser and conservative storefront link extractor."""

    def analyze(
        self,
        observation: SourceObservation,
        html: bytes | str,
    ) -> tuple[NormalizedCandidate, ...]:
        if not observation.source_url:
            return ()
        text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
        parser = _ArticleHTMLParser(observation.source_url)
        parser.feed(text)
        links = list(dict.fromkeys(parser.links))
        offer_end_at = self._extract_offer_end_at(" ".join(parser.body_text), observation.observed_at)
        headline_titles = self._headline_titles(observation.raw_title or "")
        if not links:
            title = headline_titles[0] if headline_titles else self._clean_name(observation.raw_title or "")
            if not title:
                return ()
            return (NormalizedCandidate(
                source_key=observation.source_key, platform=None, external_product_id=None,
                title=title, product_url=observation.source_url, observed_at=observation.observed_at,
                source_external_id=observation.external_id, article_url=observation.source_url,
                image_url=parser.image_url,
                offer_end_at=offer_end_at,
            ),)
        results: list[NormalizedCandidate] = []
        seen: set[tuple[str, str]] = set()
        for url, anchor_text in links:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            recognized_platform = _ArticleHTMLParser._platform(host)
            platform = recognized_platform or host
            title = self._clean_name(anchor_text)
            if not title and len(links) == 1 and len(headline_titles) == 1:
                title = self._clean_name(headline_titles[0])
            if not title:
                continue
            external_id = self._external_product_id(platform, parsed.path) if recognized_platform else None
            if not recognized_platform:
                external_id = parsed.path.rstrip("/").split("/")[-1] or hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            key = (platform or "unknown", url)
            if key in seen:
                continue
            seen.add(key)
            suffix = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
            source_external_id = f"{observation.external_id or observation.source_url}:{suffix}"
            results.append(NormalizedCandidate(
                source_key=observation.source_key,
                platform=platform if external_id else None,
                external_product_id=external_id,
                title=title,
                product_url=url,
                observed_at=observation.observed_at,
                verification_status="candidate",
                source_external_id=source_external_id,
                article_url=observation.source_url,
                image_url=parser.image_url,
                offer_end_at=offer_end_at,
                warnings=(
                    () if external_id
                    else ("store_product_id_unresolved",) if platform
                    else ("unknown_storefront_platform",)
                ),
            ))
        if not results:
            title = headline_titles[0] if headline_titles else self._clean_name(observation.raw_title or "")
            if title:
                results.append(NormalizedCandidate(
                    source_key=observation.source_key, platform=None, external_product_id=None,
                    title=title, product_url=observation.source_url, observed_at=observation.observed_at,
                    source_external_id=observation.external_id, article_url=observation.source_url,
                    image_url=parser.image_url,
                    offer_end_at=offer_end_at,
                ))
        return tuple(results)

    @staticmethod
    def _extract_offer_end_at(article_text: str, observed_at: datetime) -> datetime | None:
        """Extract one unambiguous Taiwan-local deadline with an explicit clock time."""
        pattern = re.compile(
            r"(?:期限)?(?:至|到|截止於|截止至)\s*(?:台灣時間|台北時間)?\s*"
            r"(?:(?P<year>20\d{2})年)?(?P<month>1[0-2]|0?[1-9])月"
            r"(?P<day>3[01]|[12]\d|0?[1-9])日(?P<tail>[^。；;\n]{0,28})"
        )
        matches = []
        for match in pattern.finditer(article_text):
            clock = re.search(
                r"(?P<period>凌晨|早上|上午|中午|下午|傍晚|晚上|晚間)?\s*"
                r"(?P<hour>2[0-3]|1[0-2]|0?[1-9])(?:[:：](?P<minute>[0-5]\d))?\s*點",
                match.group("tail"),
            )
            if not clock:
                continue
            hour = int(clock.group("hour"))
            period = clock.group("period")
            if period in {"下午", "傍晚", "晚上", "晚間"} and hour < 12:
                hour += 12
            elif period in {"凌晨", "早上", "上午"} and hour == 12:
                hour = 0
            elif period == "中午" and hour < 11:
                hour += 12
            elif period is None and hour < 13:
                continue
            local_tz = timezone(timedelta(hours=8))
            year = int(match.group("year")) if match.group("year") else observed_at.astimezone(local_tz).year
            try:
                deadline = datetime(year, int(match.group("month")), int(match.group("day")),
                                    hour, int(clock.group("minute") or 0), tzinfo=local_tz)
                if not match.group("year") and deadline <= observed_at.astimezone(local_tz):
                    deadline = deadline.replace(year=year + 1)
            except ValueError:
                continue
            matches.append(deadline)
        unique = list(dict.fromkeys(matches))
        return unique[0] if len(unique) == 1 else None

    @staticmethod
    def _clean_name(value: str) -> str:
        name = re.sub(r"\s+", " ", str(value or "")).strip()
        name = re.sub(r"^[\s⏩👉➡️🔗🎮：:]+", "", name)
        name = _STORE_SUFFIX_RE.sub("", name).strip(" \t-｜|：:，,。")
        name = re.sub(
            r"^(?:立即領取|前往商店|商店連結|點此前往|點此領取)\s*[:：｜|]*",
            "", name,
        ).strip(" \t-｜|：:，,。")
        if not name or name.casefold() in _GENERIC_LABELS or len(name) > 200:
            return ""
        return name

    @staticmethod
    def _headline_titles(title: str) -> list[str]:
        matches = re.findall(r"《([^《》]{1,200})》", title)
        if not matches:
            matches = re.findall(r"[「『]([^「」『』]{1,200})[」』]", title)
        return list(dict.fromkeys(item.strip() for item in matches if item.strip()))

    @staticmethod
    def _external_product_id(platform: str, path: str) -> str | None:
        if platform == "steam":
            match = re.search(r"/app/(\d+)(?:/|$)", path)
            return match.group(1) if match else None
        if platform == "epic":
            match = re.search(r"/p/([^/]+)", path)
            return match.group(1) if match else None
        if platform == "gog":
            match = re.search(r"/game/([^/]+)", path)
            return match.group(1) if match else None
        if platform == "dlsite":
            match = re.search(r"/soft/([^/]+)", path, re.IGNORECASE)
            if not match:
                match = re.search(r"/product_id/([^/]+)", path, re.IGNORECASE)
            return match.group(1) if match else None
        if platform == "ubisoft":
            parts = [part for part in path.split("/") if part]
            return parts[-1] if parts else None
        return None
