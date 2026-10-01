from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import ValidationError

from sns_harness.models import (
    ProductOffer,
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

    def generate_for_product(
        self, source: SourcePost, product: ProductOffer, existing_draft: ThreadsDraft
    ) -> ThreadsDraft: ...


class Reviewer(Protocol):
    def review(
        self, source: SourcePost, draft: ThreadsDraft, product: ProductOffer | None = None
    ) -> ReviewResult: ...


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
        retry_errors: bool = False,
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

            finder = getattr(self.queue, "find_by_source_key", None)
            if finder is None:
                finder = self.queue.find_by_tistory_id
            existing = finder(source_post.source_key)
            retry_hold = bool(
                backfill
                and existing
                and existing.status is QueueStatus.HOLD
            )
            retry_error = bool(retry_errors and existing and existing.status is QueueStatus.ERROR)
            if (
                existing
                and existing.source_hash == source_post.source_hash
                and not retry_hold
                and not retry_error
            ):
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

            existing_product = None
            if existing and getattr(existing, "has_product_input", False):
                try:
                    existing_product = existing.to_product_offer()
                except ValidationError as exc:
                    self.queue.hold_sales_request(
                        existing.page_id,
                        f"상품 정보 검증 실패: {exc}",
                    )
                    stats["updated"] += 1
                    continue
            if existing and existing_product is not None:
                draft = self.writer.generate_for_product(  # type: ignore[union-attr]
                    source_post,
                    existing_product,
                    existing.draft,
                )
                review = self.reviewer.review(  # type: ignore[union-attr]
                    source_post,
                    draft,
                    existing_product,
                )
                self.queue.replace_sales_draft(
                    existing.page_id,
                    source_post,
                    review,
                    existing_product.product_hash,
                )
                stats["updated"] += 1
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

    def prepare_sales(self, *, dry_run: bool = False) -> dict[str, int]:
        if self.source is None:
            raise RuntimeError("source adapter is required for product draft preparation")
        if not dry_run and (self.writer is None or self.reviewer is None):
            raise RuntimeError("writer and reviewer are required for product draft preparation")

        stats = {"candidates": 0, "prepared": 0, "held": 0, "skipped": 0}
        for item in self.queue.sales_draft_requests():
            stats["candidates"] += 1
            if item.published_at or item.threads_ids:
                stats["skipped"] += 1
                continue
            try:
                product = item.to_product_offer()
                if product is None:
                    raise ValueError("상품 정보가 비어 있습니다.")
            except (ValidationError, ValueError) as exc:
                stats["held"] += 1
                if not dry_run:
                    self.queue.hold_sales_request(item.page_id, f"상품 정보 검증 실패: {exc}")
                continue
            if dry_run:
                stats["prepared"] += 1
                continue

            source = self.source.fetch(item.source_url)
            draft = self.writer.generate_for_product(source, product, item.draft)  # type: ignore[union-attr]
            review = self.reviewer.review(source, draft, product)  # type: ignore[union-attr]
            self.queue.replace_sales_draft(
                item.page_id,
                source,
                review,
                product.product_hash,
            )
            if review.approved:
                stats["prepared"] += 1
            else:
                stats["held"] += 1
        return stats

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
        current_source = (
            self.source.fetch(item.source_url) if item.source_url and self.source else None
        )
        if current_source is not None and current_source.source_hash != item.source_hash:
            message = "원문이 승인 후 변경되었습니다. 동기화로 초안을 재생성해야 합니다."
            self.queue.fail(item, message)
            raise RuntimeError(message)
        try:
            product = item.to_product_offer()
        except ValidationError as exc:
            message = f"게시 직전 상품 정보 검증 실패: {exc}"
            self.queue.fail(item, message)
            raise RuntimeError(message) from exc
        if product is not None and product.product_hash != item.product_hash:
            message = "상품 정보가 승인 후 변경되었습니다. 판매 초안을 다시 생성해야 합니다."
            self.queue.fail(item, message)
            raise RuntimeError(message)
        issues = validate_draft_against_source(item.draft, current_source, product)
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
            if getattr(exc, "retryable", False):
                self.queue.retry(item, str(exc))
            else:
                self.queue.fail(item, str(exc))
            raise
        return {"scheduled": scheduled, "published": 1, "due": 1}
