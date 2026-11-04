"""Offer data supplied by the trusted 4Gamers source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class OfferVerification:
    """Normalized offer facts published by 4Gamers, not a storefront check."""

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
