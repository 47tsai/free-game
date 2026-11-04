"""Source adapter implementations."""

from free_game.adapters.base import Adapter, FetchResult, NormalizedCandidate, SourceObservation
from free_game.adapters.generic import GenericAdapter, GenericSourceConfig
from free_game.adapters.fourgamers import FourGamersAdapter

__all__ = [
    "Adapter",
    "FetchResult",
    "FourGamersAdapter",
    "GenericAdapter",
    "GenericSourceConfig",
    "NormalizedCandidate",
    "SourceObservation",
]
