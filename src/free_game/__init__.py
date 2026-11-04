"""Free Game ingestion and claim-tracking package."""

from free_game.ingestion import IngestionPipeline, IngestionResult
from free_game.registry import SourceDefinition, SourceRegistry
from free_game.runner import HTTPFetcher, SourceRunResult, SourceRunner
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
    "WriteResult",
]
