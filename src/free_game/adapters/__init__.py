"""Source adapter implementations."""

from free_game.adapters.base import Adapter, FetchResult, NormalizedCandidate, SourceObservation
from free_game.adapters.generic import GenericAdapter, GenericSourceConfig
from free_game.adapters.steam import SteamAdapter

__all__ = [
    "Adapter",
    "FetchResult",
    "GenericAdapter",
    "GenericSourceConfig",
    "NormalizedCandidate",
    "SourceObservation",
    "SteamAdapter",
]
