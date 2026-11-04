"""Shared contracts for source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FetchResult:
    source_key: str
    fetched_at: datetime
    request_url: str
    http_status: int | None = None
    payload_hash: str | None = None
    parser_version: str = "1"
    warnings: tuple[str, ...] = ()


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
    warnings: tuple[str, ...] = field(default_factory=tuple)


class Adapter(Protocol):
    """Platform-independent adapter contract; implementations do not persist data."""

    source_key: str

    def parse(self, payload: bytes | str) -> list[SourceObservation]:
        """Parse a source response while preserving source evidence."""

    def normalize(
        self,
        observations: list[SourceObservation],
    ) -> list[NormalizedCandidate]:
        """Convert observations to conservative domain candidates."""
