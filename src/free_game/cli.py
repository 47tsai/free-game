"""Command-line entry point for configured source ingestion."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from free_game.registry import SourceRegistry
from free_game.runner import SourceRunner
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
        candidates = [
            candidate
            for result in results
            if result.succeeded and result.ingestion_result is not None
            for candidate in result.ingestion_result.candidates
        ]

        write_summary = None
        if candidates:
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            if not token:
                raise RuntimeError("github_token_required_to_persist_candidates")
            writer = GitHubJsonWriter(
                GitHubContentsStore(
                    args.repository,
                    token,
                    branch=args.branch,
                )
            )
            write_result = writer.write_candidates(candidates)
            write_summary = {
                "products_created": write_result.products_created,
                "products_updated": write_result.products_updated,
                "source_records_created": write_result.source_records_created,
                "source_records_updated": write_result.source_records_updated,
                "candidates_skipped": write_result.candidates_skipped,
            }

        failures = [result for result in results if not result.succeeded]
        print(json.dumps({
            "status": "partial_failure" if failures else "success",
            "sources": len(results),
            "successful_sources": len(results) - len(failures),
            "failed_sources": [
                {"source_key": result.source_key, "error": result.error}
                for result in failures
            ],
            "candidates": len(candidates),
            "write": write_summary,
        }, ensure_ascii=False))
        return 1 if failures else 0
    except Exception as exc:
        # Avoid dumping arbitrary exception text from external integrations.
        print(json.dumps({
            "status": "error",
            "error": f"{type(exc).__name__}:ingestion_failed",
        }))
        return 1


if __name__ == "__main__":
    sys.exit(main())
