"""Conservative storefront verification for discovered free-game candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
import re

from free_game.adapters.base import NormalizedCandidate


@dataclass(frozen=True, slots=True)
class OfferVerification:
    status: str
    platform: str
    external_product_id: str
    title: str
    claim_url: str
    source_key: str
    source_external_id: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    region: str | None = None
    reason: str = ""


class EpicPromotionVerifier:
    """Verify Taiwan Epic promotions using exact product-slug matches."""

    def verify(
        self,
        candidate: NormalizedCandidate,
        payload: bytes | str,
        *,
        now: datetime | None = None,
    ) -> OfferVerification:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("verification clock must be timezone-aware")
        if candidate.platform != "epic" or not candidate.product_url:
            return self._result(candidate, "needs_review", "unsupported_candidate")

        parsed = urlparse(candidate.product_url)
        if parsed.scheme != "https" or parsed.hostname != "store.epicgames.com":
            return self._result(candidate, "needs_review", "unsupported_product_url")
        slug = self._page_slug(parsed.path)
        if not slug:
            return self._result(candidate, "needs_review", "epic_product_slug_missing")

        try:
            document = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._result(candidate, "needs_review", "epic_response_invalid")

        elements = (
            document.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
            if isinstance(document, dict) else []
        )
        if not isinstance(elements, list):
            return self._result(candidate, "needs_review", "epic_elements_invalid")

        matched = next(
            (item for item in elements if isinstance(item, dict) and self._matches_slug(item, slug)),
            None,
        )
        if matched is None:
            return self._result(candidate, "needs_review", "epic_exact_product_not_found")

        promotions = matched.get("promotions")
        if not isinstance(promotions, dict):
            return self._result(candidate, "needs_review", "epic_promotions_missing")
        groups = promotions.get("promotionalOffers")
        if not isinstance(groups, list) or not groups:
            upcoming = promotions.get("upcomingPromotionalOffers")
            if isinstance(upcoming, list) and upcoming:
                return self._result(candidate, "needs_review", "epic_offer_not_active_yet")
            return self._result(candidate, "rejected", "epic_no_active_promotion")

        price = matched.get("price")
        total = price.get("totalPrice") if isinstance(price, dict) else None
        if not isinstance(total, dict):
            return self._result(candidate, "needs_review", "epic_price_missing")
        try:
            original = int(total.get("originalPrice", 0) or 0)
            discounted = int(total.get("discountPrice", -1))
        except (TypeError, ValueError):
            return self._result(candidate, "needs_review", "epic_price_invalid")
        if original <= 0 or discounted != 0:
            return self._result(candidate, "rejected", "epic_active_offer_not_free")

        current = now.astimezone(timezone.utc)
        active_windows: list[tuple[datetime | None, datetime | None]] = []
        expired_windows = 0
        future_windows = 0
        for group in groups:
            if not isinstance(group, dict):
                continue
            offers = group.get("promotionalOffers")
            if not isinstance(offers, list):
                continue
            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                start = self._parse_date(offer.get("startDate"))
                end = self._parse_date(offer.get("endDate"))
                if start is not None and start > current:
                    future_windows += 1
                    continue
                if end is not None and end <= current:
                    expired_windows += 1
                    continue
                active_windows.append((start, end))

        if not active_windows:
            if future_windows:
                return self._result(candidate, "needs_review", "epic_offer_not_active_yet")
            if expired_windows:
                return self._result(candidate, "rejected", "epic_offer_expired")
            return self._result(candidate, "needs_review", "epic_active_window_unconfirmed")

        starts = [start for start, _ in active_windows if start is not None]
        ends = [end for _, end in active_windows if end is not None]
        start_at = min(starts) if starts else None
        end_at = min(ends) if ends else None
        return self._result(
            candidate,
            "verified",
            "epic_exact_product_active_zero_price",
            starts_at=start_at,
            ends_at=end_at,
            region="TW",
        )

    @staticmethod
    def _page_slug(path: str) -> str:
        parts = [part for part in path.split("/") if part]
        for index, part in enumerate(parts[:-1]):
            if part.lower() == "p":
                return parts[index + 1].lower()
        return ""

    @classmethod
    def _matches_slug(cls, element: dict, slug: str) -> bool:
        values = [element.get("productSlug"), element.get("urlSlug")]
        mappings = element.get("offerMappings", [])
        if isinstance(mappings, list):
            values.extend(
                item.get("pageSlug") for item in mappings if isinstance(item, dict)
            )
        return any(
            isinstance(value, str) and value.strip("/").lower() == slug
            for value in values
        )

    @staticmethod
    def _parse_date(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _result(
        candidate: NormalizedCandidate,
        status: str,
        reason: str,
        *,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        region: str | None = None,
    ) -> OfferVerification:
        return OfferVerification(
            status=status,
            platform=candidate.platform or "",
            external_product_id=candidate.external_product_id or "",
            title=candidate.title,
            claim_url=candidate.product_url or "",
            source_key=candidate.source_key,
            source_external_id=candidate.source_external_id or "",
            starts_at=starts_at,
            ends_at=ends_at,
            region=region,
            reason=reason,
        )


def verify_candidate(candidate: NormalizedCandidate, payload: bytes | str, *, now=None) -> OfferVerification:
    """Use the implemented platform verifier, otherwise keep the result for review."""
    if candidate.platform == "epic":
        return EpicPromotionVerifier().verify(candidate, payload, now=now)
    return EpicPromotionVerifier._result(candidate, "needs_review", "platform_verifier_not_implemented")
