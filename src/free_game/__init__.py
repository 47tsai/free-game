"""Free Game ingestion and claim-tracking package."""

from free_game.ingestion import IngestionPipeline, IngestionResult
from free_game.registry import SourceDefinition, SourceRegistry

__all__ = [
    "IngestionPipeline",
    "IngestionResult",
    "SourceDefinition",
    "SourceRegistry",
]
