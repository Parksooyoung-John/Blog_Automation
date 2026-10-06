from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta

import requests

from sns_harness.agents.reviewer import ComplianceReviewer
from sns_harness.agents.writer import ThreadsWriter
from sns_harness.config import Settings, get_settings
from sns_harness.operations.github_status import GitHubActionsStatus
from sns_harness.operations.manager import DailyOperationsManager
from sns_harness.operations.models import OperationsSnapshot
from sns_harness.orchestrator import HarnessOrchestrator
from sns_harness.publishers.threads import ThreadsAPIError, ThreadsPublisher
from sns_harness.queues.notion import NotionQueue
from sns_harness.queues.operations_notion import OperationsNotionQueue
from sns_harness.research.naver_datalab import NaverDataLabClient, default_date_range
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

    daily = commands.add_parser("generate-daily")
    daily.add_argument("--type", choices=("재테크팁", "질문형", "운영글"), required=True)
    daily.add_argument("--text", required=True)
    daily.add_argument("--title", default="MoneyBrief 하루 콘텐츠")
    daily.add_argument("--slot", required=True, choices=("08:30", "12:30", "16:30", "21:30"))
    daily.add_argument("--topic", default="")
    daily.add_argument("--hook", default="")
    daily.add_argument("--operator-note", default="")
    daily.add_argument("--dry-run", action="store_true")
    auto = commands.add_parser("generate-daily-auto")
    auto.add_argument("--type", choices=("재테크팁", "질문형", "운영글"), required=True)
    auto.add_argument("--slot", required=True, choices=("08:30", "12:30", "16:30", "21:30"))
    auto.add_argument("--dry-run", action="store_true")

    sync = commands.add_parser("sync")
    sync.add_argument("--source", choices=("tistory", "naver"), default="naver")
    sync.add_argument("--backfill", type=int, default=None, metavar="N")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--retry-errors", action="store_true")

    regenerate = commands.add_parser("regenerate-blog-hooks")
    regenerate.add_argument("--dry-run", action="store_true")

    publish = commands.add_parser("publish-due")
    publish.add_argument("--dry-run", action="store_true")

    prepare_sales = commands.add_parser("prepare-sales")
    prepare_sales.add_argument("--dry-run", action="store_true")
    research = commands.add_parser("research-topics")
    research.add_argument("--days", type=int, default=30)
    research.add_argument("--keyword", action="append", default=[])
    research.add_argument("--dry-run", action="store_true")
    metrics = commands.add_parser("metrics")
    metric_commands = metrics.add_subparsers(dest="metric_operation", required=True)
    metric_collect = metric_commands.add_parser("collect")
    metric_collect.add_argument("--window", choices=("24h", "72h", "7d"), required=True)
    metric_collect.add_argument("--days", type=int, default=14)
    metric_collect.add_argument("--dry-run", action="store_true")
    operations = commands.add_parser("operations")
    operation_commands = operations.add_subparsers(dest="operation", required=True)
    collect = operation_commands.add_parser("collect")
    collect.add_argument("--days", type=int, default=30)
    collect.add_argument("--dry-run", action="store_true")
    operation_commands.add_parser("data-gaps").add_argument("--days", type=int, default=30)
    brief = operation_commands.add_parser("brief")
    brief.add_argument("--date", default="today")
    brief.add_argument("--days", type=int, default=30)
    evaluate = operation_commands.add_parser("evaluate")
    evaluate.add_argument("--days", type=int, default=30)
    report = operation_commands.add_parser("report")
    report.add_argument("--days", type=int, default=30)
    operation_commands.add_parser("setup-schema")
    return root


def notion_queue(settings: Settings) -> NotionQueue:
    return NotionQueue(
        settings.notion_api_key,
        settings.notion_sns_database_id,
        timeout=settings.request_timeout_seconds,
    )


def operations_queue(settings: Settings) -> OperationsNotionQueue:
    return OperationsNotionQueue(
        settings.notion_api_key,
        settings.notion_operations_database_id,
        timeout=settings.request_timeout_seconds,
    )


def operations_snapshot(settings: Settings, days: int) -> OperationsSnapshot:
    now = datetime.now(UTC)
    items = notion_queue(settings).operations_items(now - timedelta(days=days))
    github_available = False
    github_failures = 0
    try:
        github_available, github_failures = GitHubActionsStatus(
            settings.github_token,
            settings.github_repository,
            timeout=settings.request_timeout_seconds,
        ).recent_failures()
    except requests.RequestException:
        pass
    previous_verdicts = []
    unresolved: set[str] = set()
    suppressed: set[str] = set()
    if settings.notion_operations_database_id:
        queue = operations_queue(settings)
        previous_verdicts = queue.previous_verdicts()
        unresolved, suppressed = queue.request_context()
    return OperationsSnapshot(
        generated_at=now,
        period_days=days,
        items=items,
        github_status_available=github_available,
        github_failures=github_failures,
        search_trend_available=any(item.trend_score is not None for item in items),
        unresolved_request_keys=unresolved,
        suppressed_request_keys=suppressed,
        previous_verdicts=previous_verdicts,
    )


def metric_age_hours(window: str) -> tuple[int, int]:
    return {"24h": (24, 72), "72h": (72, 168), "7d": (168, 336)}[window]


def collect_metrics(
    settings: Settings, *, window: str, days: int, dry_run: bool
) -> dict[str, object]:
    now = datetime.now(UTC)
    minimum_hours, maximum_hours = metric_age_hours(window)
    queue = notion_queue(settings)
    if not dry_run:
        queue.ensure_daily_schema()
    items = queue.operations_items(now - timedelta(days=days))
    candidates = [
        item
        for item in items
        if item.status.value == "게시완료"
        and item.threads_ids
        and item.published_at
        and minimum_hours <= (now - item.published_at).total_seconds() / 3600 < maximum_hours
        and window not in item.metrics
    ]
    result: dict[str, object] = {
        "window": window,
        "candidates": len(candidates),
        "collected": 0,
        "skipped": len(items) - len(candidates),
        "failed": 0,
        "permission_required": False,
    }
    if dry_run:
        result["dry_run"] = True
        return result

    publisher = ThreadsPublisher(
        settings.threads_user_id,
        settings.threads_access_token,
        expected_username=settings.blog_account_label,
        timeout=settings.request_timeout_seconds,
    )
    permission_errors = 0
    for item in candidates:
        try:
            metrics = publisher.post_insights(item.threads_ids[0], window=window)
            queue.update_metrics(item.page_id, metrics)
            result["collected"] = int(result["collected"]) + 1
        except ThreadsAPIError as exc:
            result["failed"] = int(result["failed"]) + 1
            if "permission" in str(exc).lower() or "scope" in str(exc).lower():
                permission_errors += 1
    result["permission_required"] = bool(candidates) and permission_errors == len(candidates)
    return result


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

    if args.command == "research-topics":
        missing = settings.missing_for("research-topics")
        if missing:
            print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
            return 2
        keywords = args.keyword
        if not keywords:
            source = NaverSource(settings.naver_blog_id, timeout=settings.request_timeout_seconds)
            keywords = [post.title[:40] for post in source.discover(limit=5)]
        groups = [(keyword, [keyword]) for keyword in keywords if keyword.strip()]
        start, end = default_date_range(args.days)
        snapshots = NaverDataLabClient(
            settings.naver_client_id,
            settings.naver_client_secret,
            timeout=settings.request_timeout_seconds,
        ).search(groups, start_date=start, end_date=end)
        print(json.dumps({
            "days": args.days,
            "results": [
                {
                    "keyword": item.group_name,
                    "trend_score": item.score,
                    "trend_direction": item.direction.value,
                    "series": list(item.series),
                }
                for item in snapshots
            ],
        }, ensure_ascii=False))
        return 0

    if args.command == "metrics":
        missing = settings.missing_for("metrics")
        if missing:
            print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
            return 2
        result = collect_metrics(
            settings,
            window=args.window,
            days=args.days,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "operations":
        if args.operation == "setup-schema":
            mode = "operations-schema"
        elif args.operation == "brief":
            mode = "operations-brief"
        else:
            mode = "operations-read"
        missing = settings.missing_for(mode)
        if missing:
            print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
            return 2
        if args.operation == "setup-schema":
            added = operations_queue(settings).ensure_schema()
            print(json.dumps({"added": added}, ensure_ascii=False, sort_keys=True))
            return 0
        evaluation = DailyOperationsManager().evaluate(
            operations_snapshot(settings, args.days)
        )
        if args.operation == "brief":
            target_day = (
                datetime.now(settings.tz).date()
                if args.date == "today"
                else date.fromisoformat(args.date)
            )
            page_id = operations_queue(settings).upsert_brief(target_day, evaluation)
            result = {"page_id": page_id, **evaluation.model_dump(mode="json")}
        elif args.operation == "data-gaps":
            result = {"data_requests": evaluation.model_dump(mode="json")["data_requests"]}
        else:
            result = evaluation.model_dump(mode="json")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    if args.command == "generate-daily":
        missing = settings.missing_for("setup-daily-schema")
        if missing:
            print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
            return 2
        if args.type == "운영글" and not args.operator_note:
            print("운영글은 --operator-note가 필요합니다.", file=sys.stderr)
            return 2
        if args.dry_run:
            print(json.dumps(
                {"dry_run": True, "type": args.type, "slot": args.slot},
                ensure_ascii=False,
            ))
            return 0
        item = notion_queue(settings).create_daily_candidate(
            title=args.title, text=args.text, content_type=args.type,
            publish_slot=args.slot, topic=args.topic, hook_type=args.hook,
            operator_note=args.operator_note,
        )
        print(json.dumps(
            {"page_id": item.page_id, "status": item.status.value}, ensure_ascii=False
        ))
        return 0

    if args.command == "generate-daily-auto":
        mode = "generate-daily-auto" if not args.dry_run else "setup-daily-schema"
        missing = settings.missing_for(mode)
        if missing:
            print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
            return 2
        queue = notion_queue(settings)
        if args.type == "운영글":
            notes = queue.pending_operator_notes()
            if not notes:
                print(json.dumps({"created": 0, "reason": "운영메모 없음"}, ensure_ascii=False))
                return 0
            if args.dry_run:
                print(json.dumps({"candidates": len(notes), "type": args.type}, ensure_ascii=False))
                return 0
            created = []
            for note in notes:
                item = queue.create_daily_candidate(
                    title=f"운영글 · {note.title}", text=note.operator_note,
                    content_type=args.type, publish_slot=args.slot,
                    topic=note.topic, hook_type="경험/공감",
                    operator_note=note.operator_note,
                )
                created.append(item.page_id)
            print(json.dumps({"created": len(created), "page_ids": created}, ensure_ascii=False))
            return 0
        source = NaverSource(settings.naver_blog_id, timeout=settings.request_timeout_seconds)
        url = source.discover(limit=1)[0]
        post = source.fetch(url)
        if args.dry_run:
            print(json.dumps(
                {"source": post.url, "type": args.type, "slot": args.slot},
                ensure_ascii=False,
            ))
            return 0
        writer = ThreadsWriter(settings.openai_api_key, settings.openai_model,
                               settings.prompt_dir / "threads_writer.md")
        draft = writer.generate_daily(post, args.type)
        item = queue.create_daily_candidate(
            title=f"{args.type} · {post.title}", text=draft.text,
            content_type=args.type, publish_slot=args.slot, topic=draft.topic,
            hook_type=draft.hook_type.value, hook_text=draft.hook_text,
        )
        print(json.dumps(
            {"page_id": item.page_id, "status": item.status.value}, ensure_ascii=False
        ))
        return 0

    if args.command == "regenerate-blog-hooks":
        missing = settings.missing_for("sync")
        if missing:
            print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
            return 2
        queue = notion_queue(settings)
        source = NaverSource(
            settings.naver_blog_id,
            timeout=settings.request_timeout_seconds,
        )
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
        result = HarnessOrchestrator(source, writer, reviewer, queue).regenerate_blog_hooks(
            dry_run=args.dry_run
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
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
            expected_username=settings.blog_account_label,
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
        if result.get("due", 0) > result.get("published", 0):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
