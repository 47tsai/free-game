import json
import re
from urllib.parse import quote, urlparse


class SteamPriceResolver:
    def __init__(self, http):
        self.http = http

    def resolve(self, name, link):
        if urlparse(link).netloc.lower() != "store.steampowered.com":
            return ""

        appid = self._appid(link)
        if appid:
            try:
                data, _ = self.http.get(
                    "https://store.steampowered.com/api/appdetails"
                    "?appids=" + appid + "&cc=tw&l=tchinese"
                )
                obj = json.loads(data).get(appid, {})
                if obj.get("success"):
                    price = self._price(obj.get("data", {}))
                    if price:
                        return price
            except Exception:
                pass

        try:
            data, _ = self.http.get(
                "https://store.steampowered.com/api/storesearch/"
                "?cc=tw&l=tchinese&term=" + quote(name)
            )
            items = json.loads(data).get("items", [])
            best = self._best_match(name, items)
            return self._price(best)
        except Exception:
            return ""

    @staticmethod
    def _price(data):
        if not isinstance(data, dict):
            return ""
        if data.get("is_free") and not isinstance(data.get("price_overview"), dict):
            return ""

        overview = data.get("price_overview")
        if isinstance(overview, dict):
            if overview.get("discount_percent", 0) > 0:
                return overview.get("initial_formatted", "") or overview.get(
                    "final_formatted", ""
                )
            return overview.get("final_formatted", "") or overview.get(
                "initial_formatted", ""
            )

        price = data.get("price")
        if isinstance(price, dict):
            if price.get("discount_percent", 0) > 0:
                return price.get("initial_formatted", "") or price.get(
                    "final_formatted", ""
                )
            return price.get("final_formatted", "") or price.get(
                "initial_formatted", ""
            )

        return ""

    @staticmethod
    def _normalize(value):
        return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value.lower()).strip()

    @classmethod
    def _best_match(cls, name, items):
        target = cls._normalize(name)
        if not target:
            return {}

        target_tokens = set(target.split())
        best = {}
        best_score = -1

        for item in items[:20]:
            title = cls._normalize(str(item.get("name", "")))
            if not title:
                continue
            if title == target:
                return item

            tokens = set(title.split())
            overlap = len(target_tokens & tokens) / max(len(target_tokens | tokens), 1)
            contains = 0.35 if target in title or title in target else 0
            score = overlap + contains
            if score > best_score:
                best, best_score = item, score

        return best if best_score >= 0.5 else {}

    @staticmethod
    def _appid(link):
        match = re.search(r"/app/(\d+)", urlparse(link).path)
        return match.group(1) if match else ""
