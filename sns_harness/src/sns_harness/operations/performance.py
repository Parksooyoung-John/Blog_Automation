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


def performance_rows(items: list[QueueItem]) -> list[dict[str, object]]:
    rows = []
    for item in items:
        value = views(item)
        if item.status is not QueueStatus.PUBLISHED or value is None or not item.draft.posts:
            continue
        rows.append({
            "published": item.published_at.date().isoformat() if item.published_at else "",
            "views": value,
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
    return {
        "measured": len(rows),
        "median_views": med(rows),
        "short_first_post": {"n": len(short), "median_views": med(short)},
        "long_first_post": {"n": len(long_), "median_views": med(long_)},
        "with_image": {"n": len(imaged), "median_views": med(imaged)},
        "enough_for_rules": len(rows) >= 30,
    }
