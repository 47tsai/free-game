"""Free Game ingestion and claim-tracking package."""

from free_game.ingestion import IngestionPipeline, IngestionResult
from free_game.registry import SourceDefinition, SourceRegistry
from free_game.runner import HTTPFetcher, SourceRunResult, SourceRunner
from free_game.verification import EpicPromotionVerifier, OfferVerification, verify_candidate
from free_game.writer import GitHubContentsStore, GitHubJsonWriter, OfferWriteResult, WriteResult

__all__ = [
    "GitHubContentsStore",
    "GitHubJsonWriter",
    "HTTPFetcher",
    "IngestionPipeline",
    "IngestionResult",
    "EpicPromotionVerifier",
    "OfferVerification",
    "OfferWriteResult",
    "SourceDefinition",
    "SourceRegistry",
    "SourceRunResult",
    "SourceRunner",
    "WriteResult",
    "verify_candidate",
]
