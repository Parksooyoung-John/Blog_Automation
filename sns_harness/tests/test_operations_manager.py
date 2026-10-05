from datetime import UTC, datetime, timedelta

from sns_harness.models import (
    ContentType,
    HookType,
    PostFormat,
    PostMetrics,
    QueueItem,
    QueueStatus,
    ThreadsDraft,
)
from sns_harness.operations.manager import PIVOT_MESSAGE, DailyOperationsManager
from sns_harness.operations.models import OperationsSnapshot, StrategyVerdict

NOW = datetime(2026, 10, 5, tzinfo=UTC)


def item(index: int, *, views: int | None = None, status=QueueStatus.PUBLISHED) -> QueueItem:
    metrics = {}
    if views is not None:
        metrics["24h"] = PostMetrics(window="24h", views=views, replies=0, reposts=0)
    return QueueItem(
        page_id=str(index),
        status=status,
        source_url=f"https://blog.naver.com/education_blog/{index}",
        source_key=f"naver:{index}",
        source_hash="hash",
        title=f"글 {index}",
        draft=ThreadsDraft(format=PostFormat.SINGLE, posts=["내용"]),
        published_at=NOW - timedelta(days=30 - index),
        threads_ids=[str(index)] if status is QueueStatus.PUBLISHED else [],
        content_type=list(ContentType)[index % len(ContentType)],
        hook_type=list(HookType)[index % len(HookType)],
        experiment_hypothesis=f"실험 {index % 3}",
        metrics=metrics,
    )


def snapshot(items, **kwargs) -> OperationsSnapshot:
    return OperationsSnapshot(generated_at=NOW, period_days=30, items=items, **kwargs)


def test_insufficient_data_never_recommends_pivot():
    result = DailyOperationsManager().evaluate(snapshot([item(i, views=10) for i in range(12)]))
    assert result.verdict is StrategyVerdict.INSUFFICIENT
    assert all(request.key != "threads-window-views" for request in result.data_requests)


def test_operational_failure_is_separated_from_content_performance():
    failed = item(99, status=QueueStatus.ERROR)
    result = DailyOperationsManager().evaluate(snapshot([failed]))
    assert result.verdict is StrategyVerdict.RECOVER
    assert "운영" in result.summary


def test_second_failed_review_uses_required_pivot_message():
    items = [item(i, views=100) for i in range(10)] + [item(i + 10, views=50) for i in range(10)]
    result = DailyOperationsManager().evaluate(
        snapshot(items, previous_verdicts=[StrategyVerdict.REVIEW_PIVOT])
    )
    assert result.verdict is StrategyVerdict.PIVOT
    assert result.summary.startswith(PIVOT_MESSAGE)


def test_suppressed_request_is_not_repeated_and_requests_are_capped():
    result = DailyOperationsManager().evaluate(
        snapshot([], suppressed_request_keys={"github-actions-read"})
    )
    assert all(request.key != "github-actions-read" for request in result.data_requests)
    assert len(result.data_requests) <= 5
