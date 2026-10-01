from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

import requests

from sns_harness.agents.reviewer import ComplianceReviewer
from sns_harness.agents.writer import ThreadsWriter
from sns_harness.config import Settings, get_settings
from sns_harness.orchestrator import HarnessOrchestrator
from sns_harness.publishers.threads import ThreadsPublisher
from sns_harness.queues.notion import NotionQueue
from sns_harness.sources.naver import NaverSource
from sns_harness.sources.router import PublishSourceRouter
from sns_harness.sources.tistory import TistorySource


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Blog to Threads publishing harness")
    commands = root.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-config")
    validate.add_argument(
        "--for-command",
        choices=("sync", "publish", "prepare-sales", "setup-daily-schema", "all"),
        default="all",
    )

    commands.add_parser("setup-daily-schema")

    sync = commands.add_parser("sync")
    sync.add_argument("--source", choices=("tistory", "naver"), default="naver")
    sync.add_argument("--backfill", type=int, default=None, metavar="N")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--retry-errors", action="store_true")

    publish = commands.add_parser("publish-due")
    publish.add_argument("--dry-run", action="store_true")

    prepare_sales = commands.add_parser("prepare-sales")
    prepare_sales.add_argument("--dry-run", action="store_true")
    return root


def notion_queue(settings: Settings) -> NotionQueue:
    return NotionQueue(
        settings.notion_api_key,
        settings.notion_sns_database_id,
        timeout=settings.request_timeout_seconds,
    )


def validate(settings: Settings, command: str) -> int:
    commands = (
        ("sync", "publish", "prepare-sales", "setup-daily-schema")
        if command == "all"
        else (command,)
    )
    missing = sorted({name for item in commands for name in settings.missing_for(item)})
    if missing:
        print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
        return 2
    try:
        errors = notion_queue(settings).validate_schema()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        if status == 404:
            print(
                "Notion database not found. Share the SNS database with the "
                "integration used by NOTION_API_KEY and verify "
                "NOTION_SNS_DATABASE_ID.",
                file=sys.stderr,
            )
        else:
            print(f"Notion API validation failed (HTTP {status}).", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"Could not connect to Notion API: {type(exc).__name__}.", file=sys.stderr)
        return 2
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    print("Configuration and Notion schema are valid.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = get_settings()

    if args.command == "validate-config":
        return validate(settings, args.for_command)

    if args.command == "setup-daily-schema":
        missing = settings.missing_for("setup-daily-schema")
        if missing:
            print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
            return 2
        added = notion_queue(settings).ensure_daily_schema()
        print(json.dumps({"added": added}, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "sync":
        mode = "sync-dry-run" if args.dry_run else "sync"
    elif args.command == "prepare-sales":
        mode = "prepare-sales-dry-run" if args.dry_run else "prepare-sales"
    else:
        mode = "publish-dry-run" if args.dry_run else "publish"
    missing = settings.missing_for(mode)
    if missing:
        print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
        return 2

    queue = notion_queue(settings)
    if args.command == "sync":
        if args.source == "naver":
            source = NaverSource(
                settings.naver_blog_id,
                timeout=settings.request_timeout_seconds,
            )
        else:
            source = TistorySource(
                settings.blog_base_url,
                timeout=settings.request_timeout_seconds,
            )
        writer = None
        reviewer = None
        if not args.dry_run:
            writer = ThreadsWriter(
                settings.openai_api_key,
                settings.openai_model,
                settings.prompt_dir / "threads_writer.md",
            )
            reviewer = ComplianceReviewer(
                settings.openai_api_key,
                settings.openai_model,
                settings.prompt_dir / "compliance_reviewer.md",
            )
        orchestrator = HarnessOrchestrator(source, writer, reviewer, queue)
        result = orchestrator.sync(
            backfill=args.backfill,
            lookback_hours=settings.sync_lookback_hours,
            dry_run=args.dry_run,
            retry_errors=args.retry_errors,
        )
    elif args.command == "publish-due":
        source = PublishSourceRouter(
            TistorySource(
                settings.blog_base_url,
                timeout=settings.request_timeout_seconds,
            ),
            NaverSource(
                settings.naver_blog_id,
                timeout=settings.request_timeout_seconds,
            ),
        )
        orchestrator = HarnessOrchestrator(source, None, None, queue)
        publisher = ThreadsPublisher(
            settings.threads_user_id,
            settings.threads_access_token,
            timeout=settings.request_timeout_seconds,
        )
        result = orchestrator.publish_due(
            publisher,
            now=datetime.now(UTC),
            slots=settings.default_slots,
            timezone=settings.tz,
            dry_run=args.dry_run,
        )
    else:
        source = PublishSourceRouter(
            TistorySource(
                settings.blog_base_url,
                timeout=settings.request_timeout_seconds,
            ),
            NaverSource(
                settings.naver_blog_id,
                timeout=settings.request_timeout_seconds,
            ),
        )
        writer = None
        reviewer = None
        if not args.dry_run:
            writer = ThreadsWriter(
                settings.openai_api_key,
                settings.openai_model,
                settings.prompt_dir / "threads_writer.md",
            )
            reviewer = ComplianceReviewer(
                settings.openai_api_key,
                settings.openai_model,
                settings.prompt_dir / "compliance_reviewer.md",
            )
        orchestrator = HarnessOrchestrator(source, writer, reviewer, queue)
        result = orchestrator.prepare_sales(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.command == "publish-due" and not args.dry_run:
        if result.get("published", 0) != 1:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
