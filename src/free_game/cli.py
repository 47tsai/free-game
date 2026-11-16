"""4Gamers RSS and FGC claim synchronization commands."""

from __future__ import annotations

import argparse
import json
import os
import sys

from free_game.adapters.fourgamers import FourGamersAdapter
from free_game.article_analysis import FourGamersArticleAnalyzer
from free_game.fgc import fetch_fgc_claims
from free_game.notifications import DiscordNotificationService, DiscordWebhookSender
from free_game.runner import HTTPFetcher
from free_game.writer import GitHubContentsStore, GitHubJsonWriter

FOUR_GAMERS_RSS = "https://www.4gamers.com.tw/rss/latest-news"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="free-game")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest", help="read 4Gamers RSS and persist free games")
    subparsers.add_parser("fgc-sync", help="sync claimed games from FGC ntfy")
    return parser


def collect_candidates(feed_payload: bytes | str, *, fetcher=None):
    adapter = FourGamersAdapter()
    observations = adapter.parse(feed_payload)
    article_fetcher = fetcher or HTTPFetcher()
    analyzer = FourGamersArticleAnalyzer()
    candidates = []
    failures = []
    skipped = []
    for observation in observations:
        try:
            response = article_fetcher.fetch(observation.source_url)
            extracted = analyzer.analyze(observation, response.body)
            if extracted:
                candidates.extend(extracted)
            else:
                diagnostics = analyzer.diagnostics(observation, response.body)
                # An article with no storefront-domain URL in any parsed
                # href/src attribute is a non-offer news item the RSS keyword
                # filter admitted (e.g. a Twitch Drops serial-code giveaway),
                # not an extraction failure. Skip it instead of failing the
                # run; an article that does carry a storefront signal but
                # yields nothing is still reported as a failure.
                error = (
                    "no_storefront_signal"
                    if diagnostics["storefront_url_attributes_seen"] == 0
                    else "no_storefront_products_extracted"
                )
                entry = {
                    "article_id": observation.external_id,
                    "error": error,
                    **diagnostics,
                }
                if error == "no_storefront_signal":
                    skipped.append(entry)
                else:
                    failures.append(entry)
        except Exception as exc:
            failures.append({
                "article_id": observation.external_id,
                "error": "article_fetch_or_analysis_failed",
                "reason": type(exc).__name__,
            })
    return candidates, failures, skipped


def _make_writer():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("github_token_required")
    repository = os.environ.get("GITHUB_REPOSITORY", "47tsai/free-game")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return GitHubJsonWriter(GitHubContentsStore(repository, token, branch=branch))


def _send_notifications(writer):
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        return {"status": "webhook_not_configured", "sent": 0, "skipped": 0, "failed": 0}
    result = DiscordNotificationService(writer, DiscordWebhookSender(webhook)).process_games()
    return {"status": result.status, "sent": result.sent, "skipped": result.skipped, "failed": result.failed}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        writer = _make_writer()
        if args.command == "fgc-sync":
            claims = fetch_fgc_claims()
            stats, _ = writer.sync_fgc_claims(claims)
            notifications = _send_notifications(writer)
            print(json.dumps({"status": "partial_failure" if notifications["failed"] else "success", "fgc_claims": len(claims), "games_created": stats[0], "games_updated": stats[1], "notifications": notifications}, ensure_ascii=False))
            return 1 if notifications["failed"] else 0

        response = HTTPFetcher().fetch(FOUR_GAMERS_RSS)
        candidates, failed_articles, skipped_articles = collect_candidates(response.body)
        write_summary = None
        if candidates:
            result = writer.write_candidates(candidates)
            write_summary = {"games_created": result.games_created, "games_updated": result.games_updated, "candidates_skipped": result.candidates_skipped}
        notifications = _send_notifications(writer)
        failed = bool(failed_articles or notifications["failed"])
        print(json.dumps({"status": "partial_failure" if failed else "success", "rss": FOUR_GAMERS_RSS, "candidates": len(candidates), "failed_articles": failed_articles, "skipped_articles": skipped_articles, "write": write_summary, "notifications": notifications}, ensure_ascii=False))
        return 1 if failed else 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {str(exc) or 'no_error_message'}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
