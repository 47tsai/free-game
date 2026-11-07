"""Extract storefront game candidates from 4Gamers article pages."""

from __future__ import annotations

import hashlib
from dataclasses import replace
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
        self.skip_tags: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.body_text: list[str] = []
        self.image_url: str | None = None
        self._active_url: str | None = None
        self._active_text: list[str] = []
        self.anchor_tags_seen = 0
        self.anchor_tags_with_href = 0
        self.anchor_tags_skipped_by_context = 0
        self.skipped_anchor_contexts: dict[str, int] = {}
        self.max_skip_depth = 0

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
            self.skip_tags.append(tag)
            self.skip_depth = len(self.skip_tags)
            self.max_skip_depth = max(self.max_skip_depth, self.skip_depth)
        if tag == "a":
            self.anchor_tags_seen += 1
            if attrs_map.get("href"):
                self.anchor_tags_with_href += 1
            if self.skip_depth:
                self.anchor_tags_skipped_by_context += 1
                context = ">".join(self.skip_tags) or "unknown"
                self.skipped_anchor_contexts[context] = self.skipped_anchor_contexts.get(context, 0) + 1
            # Some article templates emit malformed/unclosed anchors. Finish the
            # previous anchor before starting another so its href is not lost.
            self._finish_active_link()
        if tag == "a" and attrs_map.get("href") and not self.skip_depth:
            absolute = urljoin(self.base_url, unescape(attrs_map["href"]))
            parsed = urlparse(absolute)
            host = (parsed.hostname or "").lower().rstrip(".")
            article_host = (urlparse(self.base_url).hostname or "").lower().rstrip(".")
            ignored = any(host == domain or host.endswith("." + domain) for domain in _IGNORED_HOSTS)
            same_site = host == article_host or host.endswith("." + article_host)
            if parsed.scheme == "https" and host and not ignored and not same_site:
                self._active_url = urlunparse(parsed._replace(query="", fragment=""))
                self._active_text = []

    def _finish_active_link(self) -> None:
        if self._active_url:
            label = " ".join(" ".join(self._active_text).split())
            self.links.append((self._active_url, label))
            self._active_url = None
            self._active_text = []

    def close(self) -> None:
        super().close()
        # HTMLParser does not synthesize end tags for malformed source HTML.
        self._finish_active_link()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and tag in self.skip_tags:
            # Match the closing tag by name. A mismatched closing tag must not
            # accidentally close a different ignored context.
            index = len(self.skip_tags) - 1 - self.skip_tags[::-1].index(tag)
            del self.skip_tags[index:]
            self.skip_depth = len(self.skip_tags)
        if tag == "a":
            self._finish_active_link()
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
        parser.close()
        links = list(dict.fromkeys(parser.links))
        offer_end_at = self._extract_offer_end_at(" ".join(parser.body_text), observation.observed_at)
        headline_titles = self._headline_titles(observation.raw_title or "")
        if not links:
            return ()
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
        if len(results) > 1 and not re.search(
            r"(?:以下|上述|本篇|這|該)?\s*(?:兩|三|多)?款?\s*(?:遊戲|作品).{0,32}(?:皆|均|都|全部)"
            r"|(?:所有|全部)(?:的)?\s*(?:遊戲|作品)",
            " ".join(parser.body_text),
        ):
            # A deadline mentioned in a multi-game article is not necessarily
            # shared. Keep it only when the article explicitly scopes it to all games.
            results = [replace(item, offer_end_at=None) for item in results]
        return tuple(results)

    def diagnostics(self, observation: SourceObservation, html: bytes | str) -> dict[str, int | bool | str]:
        """Return bounded, non-content diagnostics for failed article extraction."""
        if not observation.source_url:
            return {"html_bytes": 0, "external_links_found": 0, "storefront_links_found": 0}
        text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
        parser = _ArticleHTMLParser(observation.source_url)
        parser.feed(text)
        parser.close()
        storefront_links = 0
        for url, _label in parser.links:
            host = (urlparse(url).hostname or "").lower().removeprefix("www.")
            if _ArticleHTMLParser._platform(host):
                storefront_links += 1
        # Compare parsed anchors with raw HTML mentions. If a storefront domain
        # exists in the response but no anchor was parsed, the next run can
        # distinguish malformed/JS-embedded markup from a challenge or wrong page.
        raw_storefront_mentions = len(re.findall(
            r"(?:store\.steampowered\.com|store\.epicgames\.com|"
            r"(?:www\.)?gog\.com|store\.ubi\.com|store\.ubisoft\.com|"
            r"(?:www\.)?dlsite\.com)",
            text,
            flags=re.IGNORECASE,
        ))
        href_attributes = len(re.findall(r"\bhref\s*=", text, flags=re.IGNORECASE))
        return {
            "html_bytes": len(text.encode("utf-8")),
            "external_links_found": len(parser.links),
            "storefront_links_found": storefront_links,
            "raw_storefront_domain_mentions": raw_storefront_mentions,
            "href_attributes_found": href_attributes,
            "body_tag_present": bool(re.search(r"<body(?:\s|>)", text, flags=re.IGNORECASE)),
            "anchor_tags_seen": parser.anchor_tags_seen,
            "anchor_tags_with_href": parser.anchor_tags_with_href,
            "anchor_tags_skipped_by_context": parser.anchor_tags_skipped_by_context,
            "max_skip_depth": parser.max_skip_depth,
            "active_skip_tags": ",".join(parser.skip_tags),
            "skipped_anchor_contexts": ",".join(
                f"{tag}:{count}" for tag, count in sorted(parser.skipped_anchor_contexts.items())
            ),
        }

    @staticmethod
    def _extract_offer_end_at(article_text: str, observed_at: datetime) -> datetime | None:
        """Extract one unambiguous Taiwan-local deadline with an explicit clock time."""
        pattern = re.compile(
            r"(?:期限)?(?:至|到|截止於|截止至)\s*(?:台灣時間|台北時間)?\s*"
            r"(?:(?P<year>20\d{2})\s*(?:年|/)\s*)?"
            r"(?P<month>1[0-2]|0?[1-9])\s*(?:月|/)\s*"
            r"(?P<day>3[01]|[12]\d|0?[1-9])\s*(?:日|號)?"
            r"(?P<tail>[^。；;\n]{0,28})"
        )
        matches = []
        for match in pattern.finditer(article_text):
            clock = re.search(
                r"(?P<period>凌晨|早上|上午|中午|下午|傍晚|晚上|晚間)?\s*"
                r"(?P<hour>2[0-3]|1[0-2]|0?[1-9])"
                r"(?:[:：](?P<minute>[0-5]\d)|\s*點(?:\s*(?P<point_minute>[0-5]\d)\s*分)?)",
                match.group("tail"),
            )
            if not clock:
                continue
            hour = int(clock.group("hour"))
            minute = int(clock.group("minute") or clock.group("point_minute") or 0)
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
                deadline = datetime(
                    year, int(match.group("month")), int(match.group("day")),
                    hour, minute, tzinfo=local_tz,
                )
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
