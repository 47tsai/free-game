"""Command-line entry point for the 4Gamers and FGC workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from free_game.article_analysis import FourGamersArticleAnalyzer
from free_game.fgc import fetch_fgc_claims
from free_game.notifications import DiscordNotificationService, DiscordWebhookSender
from free_game.registry import SourceRegistry
from free_game.runner import HTTPFetcher, SourceRunner
from free_game.writer import GitHubContentsStore, GitHubJsonWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="free-game")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="read 4Gamers RSS and persist games")
    ingest.add_argument("--config", default="config/sources.json")
    fgc = subparsers.add_parser("fgc-sync", help="sync claimed games from FGC ntfy")
    for command in (ingest, fgc):
        command.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "47tsai/free-game"))
        command.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "main"))
    return parser


def collect_candidates(results):
    """Expand 4Gamers discovery records into storefront game candidates."""
    analyzer = FourGamersArticleAnalyzer()
    article_fetcher = HTTPFetcher()
    candidates = []
    failed_articles = []
    for result in results:
        ingestion = result.ingestion_result
        if not result.succeeded or ingestion is None:
            continue
        if result.source_key != "4gamers:latest-news":
            continue
        candidates_by_id = {item.source_external_id: item for item in ingestion.candidates}
        for observation in ingestion.observations:
            fallback = candidates_by_id.get(observation.external_id)
            try:
                if not observation.source_url:
                    raise ValueError("article_url_missing")
                response = article_fetcher.fetch(observation.source_url)
                extracted = analyzer.analyze(observation, response.body)
                candidates.extend(extracted or ((fallback,) if fallback else ()))
            except Exception:
                failed_articles.append({"source_key": result.source_key, "article_id": observation.external_id, "error": "article_fetch_or_analysis_failed"})
                if fallback:
                    candidates.append(fallback)
    return candidates, failed_articles


def _make_writer(args):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("github_token_required")
    return GitHubJsonWriter(GitHubContentsStore(args.repository, token, branch=args.branch))


def _send_notifications(writer):
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        return {"status": "webhook_not_configured", "sent": 0, "skipped": 0, "failed": 0}
    result = DiscordNotificationService(writer, DiscordWebhookSender(webhook)).process_games()
    return {"status": result.status, "sent": result.sent, "skipped": result.skipped, "failed": result.failed}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fgc-sync":
            writer = _make_writer(args)
            claims = fetch_fgc_claims()
            stats, _ = writer.sync_fgc_claims(claims)
            notifications = _send_notifications(writer)
            print(json.dumps({"status": "partial_failure" if notifications["failed"] else "success", "fgc_claims": len(claims), "games_created": stats[0], "games_updated": stats[1], "notifications": notifications}, ensure_ascii=False))
            return 1 if notifications["failed"] else 0

        registry = SourceRegistry.load(Path(args.config))
        enabled = [item for item in registry.definitions if item.enabled]
        if not enabled:
            print(json.dumps({"status": "no_enabled_sources", "sources": 0, "candidates": 0}))
            return 0
        writer = _make_writer(args)
        results = SourceRunner(registry).run_all()
        candidates, failed_articles = collect_candidates(results)
        write_summary = None
        if candidates:
            result = writer.write_candidates(candidates)
            write_summary = {"products_created": result.products_created, "products_updated": result.products_updated, "games_created": result.games_created, "source_records_created": result.source_records_created, "source_records_updated": result.source_records_updated, "candidates_skipped": result.candidates_skipped}
        notifications = _send_notifications(writer)
        failures = [item for item in results if not item.succeeded]
        failed = bool(failures or failed_articles or notifications["failed"])
        print(json.dumps({"status": "partial_failure" if failed else "success", "sources": len(results), "successful_sources": len(results) - len(failures), "failed_sources": [{"source_key": item.source_key, "error": item.error} for item in failures], "failed_articles": failed_articles, "candidates": len(candidates), "write": write_summary, "notifications": notifications}, ensure_ascii=False))
        return 1 if failed else 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}:ingestion_failed"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
