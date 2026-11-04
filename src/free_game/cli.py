"""Command-line entry point for configured source ingestion."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from free_game.article_analysis import FourGamersArticleAnalyzer
from free_game.notifications import DiscordNotificationService, DiscordWebhookSender
from free_game.verification import OfferVerification
from free_game.registry import SourceRegistry
from free_game.runner import HTTPFetcher, SourceRunner
from free_game.writer import GitHubContentsStore, GitHubJsonWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="free-game")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="fetch configured sources and persist candidates")
    ingest.add_argument("--config", default="config/sources.json")
    ingest.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", "47tsai/free-game"),
    )
    ingest.add_argument(
        "--branch",
        default=os.environ.get("GITHUB_REF_NAME", "main"),
    )
    return parser



def collect_candidates(results):
    """Expand 4Gamers discovery records into platform product candidates."""
    analyzer = FourGamersArticleAnalyzer()
    article_fetcher = HTTPFetcher()
    candidates = []
    failed_articles = []

    for result in results:
        ingestion = result.ingestion_result
        if not result.succeeded or ingestion is None:
            continue
        if result.source_key != "4gamers:latest-news":
            candidates.extend(ingestion.candidates)
            continue

        candidates_by_id = {
            candidate.source_external_id: candidate
            for candidate in ingestion.candidates
        }
        for observation in ingestion.observations:
            fallback = candidates_by_id.get(observation.external_id)
            try:
                if not observation.source_url:
                    raise ValueError("article_url_missing")
                response = article_fetcher.fetch(observation.source_url)
                extracted = analyzer.analyze(observation, response.body)
                candidates.extend(extracted or ((fallback,) if fallback else ()))
            except Exception:
                failed_articles.append({
                    "source_key": result.source_key,
                    "article_id": observation.external_id,
                    "error": "article_fetch_or_analysis_failed",
                })
                if fallback:
                    candidates.append(fallback)

    return candidates, failed_articles



def source_offers(candidates):
    """Trust free-game details curated and published by 4Gamers."""
    return [
        OfferVerification(
            status="verified",
            platform=item.platform,
            external_product_id=item.external_product_id,
            title=item.title,
            claim_url=item.product_url,
            source_key=item.source_key,
            source_external_id=item.source_external_id,
            starts_at=item.offer_start_at,
            ends_at=item.offer_end_at,
            reason="published_by_4gamers",
        )
        for item in candidates
        if item.source_key == "4gamers:latest-news"
        and item.platform and item.external_product_id and item.product_url
        and item.source_external_id
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "ingest":
        return 2

    try:
        registry = SourceRegistry.load(Path(args.config))
        enabled = [item for item in registry.definitions if item.enabled]
        if not enabled:
            print(json.dumps({
                "status": "no_enabled_sources",
                "sources": 0,
                "candidates": 0,
            }))
            return 0

        results = SourceRunner(registry).run_all()
        candidates, failed_articles = collect_candidates(results)

        write_summary = None
        notification_summary = {"status": "webhook_not_configured", "sent": 0, "skipped": 0, "failed": 0}
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
        writer = None

        if candidates or webhook_url:
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            if not token:
                raise RuntimeError("github_token_required_for_catalog_or_notifications")
            writer = GitHubJsonWriter(
                GitHubContentsStore(
                    args.repository,
                    token,
                    branch=args.branch,
                )
            )

        if candidates and writer is not None:
            write_result = writer.write_candidates(candidates)
            verifications = source_offers(candidates)
            offer_result = (
                writer.write_verified_offers(verifications)
                if verifications else None
            )
            write_summary = {
                "products_created": write_result.products_created,
                "products_updated": write_result.products_updated,
                "games_created": write_result.games_created,
                "products_linked_to_games": write_result.products_linked_to_games,
                "source_records_created": write_result.source_records_created,
                "source_records_updated": write_result.source_records_updated,
                "candidates_skipped": write_result.candidates_skipped,
                "offers_created": offer_result.offers_created if offer_result else 0,
                "offers_updated": offer_result.offers_updated if offer_result else 0,
                "offers_skipped": offer_result.offers_skipped if offer_result else 0,
            }

        if webhook_url and writer is not None:
            notification = DiscordNotificationService(
                writer, DiscordWebhookSender(webhook_url)
            ).send_new_active_offers()
            notification_summary = {
                "status": notification.status,
                "sent": notification.sent,
                "skipped": notification.skipped,
                "failed": notification.failed,
            }

        failures = [result for result in results if not result.succeeded]
        print(json.dumps({
            "status": "partial_failure" if failures or failed_articles or notification_summary["failed"] else "success",
            "sources": len(results),
            "successful_sources": len(results) - len(failures),
            "failed_sources": [
                {"source_key": result.source_key, "error": result.error}
                for result in failures
            ],
            "failed_articles": failed_articles,
            "candidates": len(candidates),
            "write": write_summary,
            "notifications": notification_summary,
        }, ensure_ascii=False))
        return 1 if failures or failed_articles or notification_summary["failed"] else 0
    except Exception as exc:
        # Avoid dumping arbitrary exception text from external integrations.
        print(json.dumps({
            "status": "error",
            "error": f"{type(exc).__name__}:ingestion_failed",
        }))
        return 1


if __name__ == "__main__":
    sys.exit(main())
