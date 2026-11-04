"""Free Game ingestion and claim-tracking package."""

from free_game.ingestion import IngestionPipeline, IngestionResult
from free_game.registry import SourceDefinition, SourceRegistry
from free_game.adapters.steam import SteamAdapter
from free_game.runner import HTTPFetcher, SourceRunResult, SourceRunner

__all__ = [
    "HTTPFetcher",
    "IngestionPipeline",
    "IngestionResult",
    "SourceDefinition",
    "SourceRegistry",
    "SourceRunResult",
    "SourceRunner",
    "SteamAdapter",
]
