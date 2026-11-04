"""Free Game ingestion and claim-tracking package."""

from free_game.adapters.steam import SteamAdapter
from free_game.ingestion import IngestionPipeline, IngestionResult
from free_game.registry import SourceDefinition, SourceRegistry
from free_game.runner import HTTPFetcher, SourceRunResult, SourceRunner
from free_game.steam_price import SteamAppDetailsAssessor, SteamPriceAssessment, SteamPriceStatus
from free_game.writer import GitHubContentsStore, GitHubJsonWriter, WriteResult

__all__ = [
    "GitHubContentsStore",
    "GitHubJsonWriter",
    "HTTPFetcher",
    "IngestionPipeline",
    "IngestionResult",
    "SourceDefinition",
    "SourceRegistry",
    "SourceRunResult",
    "SourceRunner",
    "SteamAdapter",
    "SteamAppDetailsAssessor",
    "SteamPriceAssessment",
    "SteamPriceStatus",
    "WriteResult",
]
