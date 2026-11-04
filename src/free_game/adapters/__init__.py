"""Source adapter implementations."""

from free_game.adapters.base import Adapter, FetchResult, NormalizedCandidate, SourceObservation
from free_game.adapters.generic import GenericAdapter, GenericSourceConfig

__all__ = [
    "Adapter",
    "FetchResult",
    "GenericAdapter",
    "GenericSourceConfig",
    "NormalizedCandidate",
    "SourceObservation",
]
