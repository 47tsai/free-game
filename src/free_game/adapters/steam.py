"""Steam Store featured-category adapter.

The Storefront endpoint is unofficial/undocumented. This adapter only emits
candidate records for zero-priced, 100%-discounted game apps in the specials
bucket. It never marks an offer as verified.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from free_game.adapters.base import NormalizedCandidate, SourceObservation


class SteamAdapter:
    """Parse Steam Store featured-categories JSON conservatively."""

    def __init__(
        self,
        source_key: str = "steam:featured-categories",
        source_url: str = "https://store.steampowered.com/api/featuredcategories/?cc=tw&l=tchinese",
    ) -> None:
        if not source_key.strip():
            raise ValueError("source_key must not be empty")
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or parsed.netloc != "store.steampowered.com":
            raise ValueError("Steam source_url must use HTTPS on store.steampowered.com")
        self.source_key = source_key
        self.source_url = source_url

    def parse(self, payload: bytes | str) -> list[SourceObservation]:
        text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
        try:
            document: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid Steam featured-categories JSON: {exc.msg}") from exc

        if not isinstance(document, dict):
            raise ValueError("Steam featured-categories response must be an object")
        if document.get("status") not in (None, 1, "1"):
            raise ValueError("Steam featured-categories response status is not successful")

        specials = document.get("specials")
        if not isinstance(specials, dict):
            raise ValueError("Steam response does not contain a specials bucket")
        items = specials.get("items")
        if not isinstance(items, list):
            raise ValueError("Steam specials bucket does not contain an items array")

        observed_at = datetime.now(timezone.utc)
        observations: list[SourceObservation] = []
        for item in items:
            if not isinstance(item, dict) or not self._is_free_to_keep_candidate(item):
                continue

            app_id = self._positive_int(item.get("id"))
            title = item.get("name")
            if app_id is None or not isinstance(title, str) or not title.strip():
                continue

            product_url = f"https://store.steampowered.com/app/{app_id}/"
            observations.append(SourceObservation(
                source_key=self.source_key,
                external_id=str(app_id),
                observed_at=observed_at,
                source_url=product_url,
                raw_title=title.strip(),
                raw_description=None,
                raw_data_excerpt=json.dumps(item, ensure_ascii=False, separators=(",", ":"))[:2000],
                warnings=("zero_price_offer_requires_storefront_verification",),
            ))
        return observations

    def normalize(
        self,
        observations: list[SourceObservation],
    ) -> list[NormalizedCandidate]:
        candidates: list[NormalizedCandidate] = []
        for item in observations:
            app_id = self._positive_int(item.external_id)
            title = (item.raw_title or "").strip()
            if app_id is None or not title:
                continue
            candidates.append(NormalizedCandidate(
                source_key=self.source_key,
                platform="steam",
                external_product_id=str(app_id),
                title=title,
                product_url=f"https://store.steampowered.com/app/{app_id}/",
                observed_at=item.observed_at,
                verification_status="candidate",
                source_external_id=item.external_id,
                warnings=tuple(item.warnings),
            ))
        return candidates

    @classmethod
    def _is_free_to_keep_candidate(cls, item: dict[str, Any]) -> bool:
        # Steam featured categories can contain DLC/bundles and ordinary F2P
        # products. Require a game app and explicit 100% discount from a
        # positive original price; later storefront verification is mandatory.
        if cls._positive_int(item.get("id")) is None:
            return False
        if item.get("type", 0) != 0:
            return False
        if item.get("discounted") is not True:
            return False
        if cls._non_negative_int(item.get("discount_percent")) != 100:
            return False
        if cls._non_negative_int(item.get("final_price")) != 0:
            return False
        original_price = cls._positive_int(item.get("original_price"))
        return original_price is not None

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _non_negative_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None
