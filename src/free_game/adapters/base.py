"""Data structures shared by the 4Gamers parser and article analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SourceObservation:
    source_key: str
    external_id: str | None
    observed_at: datetime
    source_url: str | None
    raw_title: str | None
    raw_description: str | None = None
    raw_data_excerpt: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizedCandidate:
    source_key: str
    platform: str | None
    external_product_id: str | None
    title: str
    product_url: str | None
    observed_at: datetime
    offer_start_at: datetime | None = None
    offer_end_at: datetime | None = None
    verification_status: str = "candidate"
    source_external_id: str | None = None
    warnings: tuple[str, ...] = ()
    article_url: str | None = None
    image_url: str | None = None
