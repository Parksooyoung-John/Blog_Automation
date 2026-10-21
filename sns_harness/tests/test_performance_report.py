from datetime import UTC, datetime

from sns_harness.models import HookType, PostFormat, PostMetrics, QueueItem, QueueStatus, ThreadsDraft
from sns_harness.operations.performance import performance_rows, summarize, views


def item(index, first, **metrics):
    return QueueItem(
        page_id=str(index), status=QueueStatus.PUBLISHED, source_url="u",
        source_key=f"naver:{index}", source_hash="h", title=f"글 {index}",
        draft=ThreadsDraft(format=PostFormat.SINGLE, posts=[first]),
        published_at=datetime(2026, 10, index, tzinfo=UTC),
        metrics={w: PostMetrics(window=w, views=v) for w, v in metrics.items()},
    )


def test_24h_is_preferred_over_later_windows():
    assert views(item(1, "가", **{"24h": 4703, "7d": 4713})) == 4703


def test_engagement_and_hook_breakdown_and_link_clicks():
    a = item(1, "가" * 30)
    a.metrics["24h"] = PostMetrics(window="24h", views=1000, likes=20, replies=5, reposts=3, quotes_shares=2)
    a.hook_type = HookType.NUMBER
    a.blog_link_used = True
    a.source_url = "https://blog.naver.com/e/1"
    rows = performance_rows([a], {"https://blog.naver.com/e/1": 12})
    assert rows[0]["engagement"] == 0.03 and rows[0]["link_clicks"] == 12
    assert summarize(rows)["by_hook"]["숫자"] == {"n": 1, "median_views": 1000, "median_engagement": 0.03}
    assert performance_rows([a])[0]["link_clicks"] is None   # no Threads lookup -> unknown, not 0


def test_report_splits_short_and_long_first_posts_and_skips_unmeasured():
    items = [
        item(1, "가" * 30, **{"24h": 900}),
        item(2, "가" * 30, **{"24h": 100}),
        item(3, "가" * 90, **{"24h": 10}),
        item(4, "가" * 30),
    ]
    rows = performance_rows(items)
    summary = summarize(rows)
    assert [row["views"] for row in rows] == [900, 100, 10]
    assert summary["short_first_post"] == {"n": 2, "median_views": 500}
    assert summary["long_first_post"] == {"n": 1, "median_views": 10}
    assert summary["enough_for_rules"] is False
