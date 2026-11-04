"""Shared, side-effect-free ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from free_game.adapters.base import Adapter, NormalizedCandidate, SourceObservation


@dataclass(frozen=True, slots=True)
class CandidateIssue:
    """A candidate rejected from this run, with a machine-readable reason."""

    source_key: str
    source_external_id: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Output of one adapter run; persistence and publishing are separate steps."""

    source_key: str
    observations: tuple[SourceObservation, ...]
    candidates: tuple[NormalizedCandidate, ...]
    issues: tuple[CandidateIssue, ...]


class IngestionPipeline:
    """Run the common parse, normalize, validate, and deduplicate stages.

    This class deliberately performs no network requests, persistence, entity
    matching, offer verification, or notification delivery.
    """

    def run(self, adapter: Adapter, payload: bytes | str) -> IngestionResult:
        observations = tuple(adapter.parse(payload))
        candidates = adapter.normalize(list(observations))

        accepted: list[NormalizedCandidate] = []
        issues: list[CandidateIssue] = []
        seen_source_records: set[tuple[str, str]] = set()

        for candidate in candidates:
            reason = self._validation_error(adapter.source_key, candidate)
            if reason is not None:
                issues.append(
                    CandidateIssue(
                        source_key=candidate.source_key,
                        source_external_id=candidate.source_external_id,
                        reason=reason,
                    )
                )
                continue

            external_id = candidate.source_external_id
            if external_id:
                natural_key = (candidate.source_key, external_id)
                if natural_key in seen_source_records:
                    issues.append(
                        CandidateIssue(
                            source_key=candidate.source_key,
                            source_external_id=external_id,
                            reason="duplicate_source_record",
                        )
                    )
                    continue
                seen_source_records.add(natural_key)

            accepted.append(candidate)

        return IngestionResult(
            source_key=adapter.source_key,
            observations=observations,
            candidates=tuple(accepted),
            issues=tuple(issues),
        )

    @staticmethod
    def _validation_error(
        adapter_source_key: str,
        candidate: NormalizedCandidate,
    ) -> str | None:
        if candidate.source_key != adapter_source_key:
            return "source_key_mismatch"
        if not candidate.title or not candidate.title.strip():
            return "missing_title"
        if not candidate.source_key.strip():
            return "missing_source_key"
        if not isinstance(candidate.observed_at, datetime):
            return "invalid_observed_at"
        if candidate.observed_at.tzinfo is None or candidate.observed_at.utcoffset() is None:
            return "observed_at_must_be_timezone_aware"
        if candidate.offer_start_at is not None:
            if candidate.offer_start_at.tzinfo is None or candidate.offer_start_at.utcoffset() is None:
                return "offer_start_at_must_be_timezone_aware"
        if candidate.offer_end_at is not None:
            if candidate.offer_end_at.tzinfo is None or candidate.offer_end_at.utcoffset() is None:
                return "offer_end_at_must_be_timezone_aware"
        if (
            candidate.offer_start_at is not None
            and candidate.offer_end_at is not None
            and candidate.offer_end_at < candidate.offer_start_at
        ):
            return "offer_end_before_start"
        if candidate.product_url is not None:
            parsed = urlparse(candidate.product_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return "invalid_product_url"
        if candidate.external_product_id is not None and not candidate.external_product_id.strip():
            return "empty_external_product_id"
        if candidate.platform is not None and not candidate.platform.strip():
            return "empty_platform"
        if candidate.verification_status != "candidate":
            return "adapter_cannot_set_verification_status"
        return None
