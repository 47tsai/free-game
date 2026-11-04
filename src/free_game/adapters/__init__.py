"""4Gamers RSS adapter and shared game data structures."""

from free_game.adapters.base import NormalizedCandidate, SourceObservation
from free_game.adapters.fourgamers import FourGamersAdapter

__all__ = ["FourGamersAdapter", "NormalizedCandidate", "SourceObservation"]
