from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from sns_harness.models import (
    QueueStatus,
    ReviewResult,
    SourcePost,
    ThreadsDraft,
    validate_draft_against_source,
)
from sns_harness.scheduling.slots import next_available_slots


class Source(Protocol):
    def discover(self, limit: int = 20) -> list[str]: ...

    def fetch(self, url: str) -> SourcePost: ...


class Writer(Protocol):
    def generate(self, source: SourcePost) -> ThreadsDraft: ...


class Reviewer(Protocol):
    def review(self, source: SourcePost, draft: ThreadsDraft) -> ReviewResult: ...


class HarnessOrchestrator:
    def __init__(
        self,
        source: Source | None,
        writer: Writer | None,
        reviewer: Reviewer | None,
        queue: object,
    ) -> None:
        self.source = source
        self.writer = writer
        self.reviewer = reviewer
        self.queue = queue

    def sync(
        self,
        *,
        backfill: int | None = None,
        lookback_hours: int = 48,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> dict[str, int]:
        if self.source is None:
            raise RuntimeError("source adapter is required for sync")
        if not dry_run and (self.writer is None or self.reviewer is None):
            raise RuntimeError("writer and reviewer are required for a mutating sync")
        current = now or datetime.now(UTC)
        limit = backfill or 20
        cutoff = None if backfill else current - timedelta(hours=lookback_hours)
        stats = {"discovered": 0, "created": 0, "updated": 0, "unchanged": 0, "skipped": 0}

        for url in self.source.discover(limit):
            source_post = self.source.fetch(url)
            stats["discovered"] += 1
            if cutoff and source_post.published_at.astimezone(UTC) < cutoff:
                stats["skipped"] += 1
                continue

            existing = self.queue.find_by_tistory_id(source_post.tistory_id)
            if existing and existing.source_hash == source_post.source_hash:
                stats["unchanged"] += 1
                continue
            if existing and existing.status is QueueStatus.PUBLISHED:
                if not dry_run:
                    self.queue.update_source_hash(existing.page_id, source_post.source_hash)
                stats["updated"] += 1
                continue
            if dry_run:
                stats["updated" if existing else "created"] += 1
                continue

            draft = self.writer.generate(source_post)  # type: ignore[union-attr]
            review = self.reviewer.review(source_post, draft)  # type: ignore[union-attr]
            if existing:
                self.queue.replace_draft(existing.page_id, source_post, review)
                stats["updated"] += 1
            else:
                self.queue.create(source_post, review)
                stats["created"] += 1
        return stats

    def schedule_approved(self, now: datetime, slots: tuple[str, ...], timezone: object) -> int:
        items = self.queue.approved_without_schedule()
        if not items:
            return 0
        occupied = self.queue.occupied_schedule_times(now)
        allocated = next_available_slots(now, occupied, slots, len(items), timezone)
        for item, scheduled_at in zip(items, allocated, strict=True):
            self.queue.set_schedule(item.page_id, scheduled_at)
        return len(items)

    def publish_due(
        self,
        publisher: object,
        *,
        now: datetime,
        slots: tuple[str, ...],
        timezone: object,
        dry_run: bool = False,
    ) -> dict[str, int]:
        if dry_run:
            return {"scheduled": 0, "published": 0, "due": len(self.queue.due(now, limit=1))}

        scheduled = self.schedule_approved(now, slots, timezone)
        due = self.queue.due(now, limit=1)
        if not due:
            return {"scheduled": scheduled, "published": 0, "due": 0}

        item = due[0]
        if self.source is None:
            raise RuntimeError("source adapter is required for publish-time validation")
        current_source = self.source.fetch(item.source_url)
        if current_source.source_hash != item.source_hash:
            message = "원문이 승인 후 변경되었습니다. 동기화로 초안을 재생성해야 합니다."
            self.queue.fail(item, message)
            raise RuntimeError(message)
        issues = validate_draft_against_source(item.draft, current_source)
        if issues:
            message = "게시 직전 검증 실패: " + "; ".join(issues)
            self.queue.fail(item, message)
            raise RuntimeError(message)
        if not self.queue.claim(item):
            return {"scheduled": scheduled, "published": 0, "due": 0}
        try:
            ids = publisher.publish(
                item,
                save_progress=lambda value: self.queue.save_progress(item.page_id, value),
            )
            self.queue.complete(item.page_id, ids, now)
        except Exception as exc:
            self.queue.fail(item, str(exc))
            raise
        return {"scheduled": scheduled, "published": 1, "due": 1}
