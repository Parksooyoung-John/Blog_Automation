from __future__ import annotations

from statistics import median

from sns_harness.models import QueueItem, QueueStatus

# 24h value is already ~99% of the 7d value (4,703 vs 4,713 on 2026-10-04), so judge on it first.
WINDOWS = ("24h", "72h", "7d")
SHORT_HOOK_CHARS = 40


def views(item: QueueItem) -> int | None:
    for window in WINDOWS:
        metric = item.metrics.get(window)
        if metric and metric.views is not None:
            return metric.views
    return None


def engagement(item: QueueItem) -> float | None:
    """(likes + replies + reposts + quotes/shares) / views, from the same window as `views`."""
    for window in WINDOWS:
        metric = item.metrics.get(window)
        if metric and metric.views:
            total = sum(
                v or 0 for v in (metric.likes, metric.replies, metric.reposts, metric.quotes_shares)
            )
            return round(total / metric.views, 4)
    return None


def performance_rows(
    items: list[QueueItem], link_clicks: dict[str, int] | None = None
) -> list[dict[str, object]]:
    rows = []
    for item in items:
        value = views(item)
        if item.status is not QueueStatus.PUBLISHED or value is None or not item.draft.posts:
            continue
        rows.append({
            "published": item.published_at.date().isoformat() if item.published_at else "",
            "views": value,
            "engagement": engagement(item),
            # clicks on the shared URL since publish; None = not looked up (no Threads credentials)
            "link_clicks": (link_clicks or {}).get(item.source_url) if item.blog_link_used and link_clicks is not None else None,
            "first_chars": len(item.draft.posts[0]),
            "hook": item.hook_type.value if item.hook_type else "",
            "link": item.blog_link_used,
            "image": item.thumbnail_status in {"준비", "완료"},
            "posts": len(item.draft.posts),
            "title": item.title[:40],
        })
    return sorted(rows, key=lambda row: str(row["published"]))


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    def med(group: list[dict[str, object]]) -> float | None:
        return median(int(row["views"]) for row in group) if group else None  # type: ignore[call-overload]

    short = [row for row in rows if int(row["first_chars"]) <= SHORT_HOOK_CHARS]  # type: ignore[call-overload]
    long_ = [row for row in rows if int(row["first_chars"]) > SHORT_HOOK_CHARS]  # type: ignore[call-overload]
    imaged = [row for row in rows if row["image"]]
    by_hook = {}
    for hook in sorted({str(row["hook"]) for row in rows}):
        group = [row for row in rows if row["hook"] == hook]
        rates = [row["engagement"] for row in group if row["engagement"] is not None]
        by_hook[hook or "(없음)"] = {
            "n": len(group), "median_views": med(group),
            "median_engagement": median(rates) if rates else None,
        }
    return {
        "by_hook": by_hook,
        "measured": len(rows),
        "median_views": med(rows),
        "short_first_post": {"n": len(short), "median_views": med(short)},
        "long_first_post": {"n": len(long_), "median_views": med(long_)},
        "with_image": {"n": len(imaged), "median_views": med(imaged)},
        "enough_for_rules": len(rows) >= 30,
    }
