from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Protocol

from pydantic import ValidationError

from sns_harness.models import (
    CandidateType,
    ProductOffer,
    QueueStatus,
    ReviewResult,
    SourcePost,
    ThreadsDraft,
    candidate_key,
    validate_draft_against_source,
)
from sns_harness.scheduling.slots import next_available_slots
from sns_harness.thumbnails import ThumbnailError


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


MIN_PUBLISH_SCORE = 7


def _differing_dimensions(a: ThreadsDraft, b: ThreadsDraft) -> int:
    """How many of first sentence, core claim, CTA and hook type differ between two drafts."""

    def differs(x: str, y: str) -> bool:
        normalize = lambda text: re.sub(r"\W+", "", text).lower()  # noqa: E731
        return SequenceMatcher(None, normalize(x), normalize(y)).ratio() < 0.8

    return sum(
        (
            differs(a.hook_text, b.hook_text),
            differs(a.core_claim, b.core_claim),
            a.blog_link_used != b.blog_link_used,
            a.hook_type != b.hook_type,
        )
    )


def pick_pair(reviews: list[ReviewResult]) -> list[ReviewResult]:
    """Top two approved candidates scoring at least MIN_PUBLISH_SCORE.

    The first is the best 정보형; the second prefers 정보+공감형 / 블로그전환형, shares at most
    one link with the first and differs from it in at least two dimensions.
    """
    worthy = sorted(
        (r for r in reviews if r.approved and _score(r) >= MIN_PUBLISH_SCORE),
        key=lambda r: (_score(r), r.quality_score),
        reverse=True,
    )
    if not worthy:
        return []
    first = next(
        (r for r in worthy if r.reviewed_draft.candidate_type is CandidateType.INFO), worthy[0]
    )
    rest = [
        r
        for r in worthy
        if r is not first
        and not (r.reviewed_draft.blog_link_used and first.reviewed_draft.blog_link_used)
        and _differing_dimensions(first.reviewed_draft, r.reviewed_draft) >= 2
    ]
    wanted = {CandidateType.INFO_EMPATHY, CandidateType.BLOG_CONVERSION}
    second = next((r for r in rest if r.reviewed_draft.candidate_type in wanted), None)
    second = second or next(iter(rest), None)
    return [first] + ([second] if second else [])


def _score(review: ReviewResult) -> int:
    # Unscored drafts (older writers, tests) pass: only an explicit low score blocks.
    score = review.reviewed_draft.score
    return MIN_PUBLISH_SCORE if score is None else score


class HarnessOrchestrator:
    def __init__(
        self,
        source: Source | None,
        writer: Writer | None,
        reviewer: Reviewer | None,
        queue: object,
        thumbnail_resolver: object | None = None,
    ) -> None:
        self.source = source
        self.writer = writer
        self.reviewer = reviewer
        self.queue = queue
        self.thumbnail_resolver = thumbnail_resolver

    def _generate_blog_reviews(
        self, source: SourcePost, now: datetime
    ) -> list[ReviewResult]:
        """Review every candidate and keep the best two; empty when none reaches the score bar."""
        policy = getattr(self.queue, "blog_generation_policy", None)
        allow_link = bool(policy(now)["allow_link"]) if policy is not None else True
        candidate_generator = getattr(self.writer, "generate_candidates", None)
        if candidate_generator is None:
            candidates = [self.writer.generate(source)]  # type: ignore[union-attr]
        else:
            candidates = candidate_generator(source, allow_link=allow_link)
        reviews = []
        for draft in candidates:
            review = self.reviewer.review(source, draft)  # type: ignore[union-attr]
            # The reviewer round-trips the draft through the model; keep the writer's own judgement.
            kept = review.reviewed_draft.model_copy(
                update={
                    "score": draft.score,
                    "visual": draft.visual,
                    "candidate_type": draft.candidate_type,
                    "core_claim": draft.core_claim,
                }
            )
            reviews.append(review.model_copy(update={"reviewed_draft": kept}))
        if any(review.approved for review in reviews):
            return pick_pair(reviews)
        return [max(reviews, key=lambda review: review.quality_score)]   # held for the operator

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
        stats = {
            "discovered": 0, "created": 0, "updated": 0, "unchanged": 0, "skipped": 0,
            "below_threshold": 0,
        }

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

            reviews = self._generate_blog_reviews(source_post, current)
            if not reviews:
                stats["below_threshold"] += 1
                continue
            for variant, review in enumerate(reviews):
                # Only the second candidate passes `variant`; single-candidate writers keep the
                # original queue call.
                extra = {"variant": variant} if variant else {}
                if variant == 0:
                    page = existing
                else:
                    page = finder(candidate_key(source_post.source_key, variant))
                if page and page.status is QueueStatus.PUBLISHED:
                    continue
                if page:
                    self.queue.replace_draft(page.page_id, source_post, review, **extra)
                    stats["updated"] += 1
                else:
                    self.queue.create(source_post, review, **extra)
                    stats["created"] += 1
        return stats

    def regenerate_blog_hooks(
        self, *, dry_run: bool = False, now: datetime | None = None
    ) -> dict[str, object]:
        if self.source is None or self.writer is None or self.reviewer is None:
            raise RuntimeError("source, writer, and reviewer are required")
        current = now or datetime.now(UTC)
        items = self.queue.unpublished_blog_items()
        results: list[dict[str, object]] = []
        generated: dict[str, list[ReviewResult]] = {}
        for item in items:
            source = self.source.fetch(item.source_url)
            if source.url not in generated:
                generated[source.url] = self._generate_blog_reviews(source, current)
            reviews = generated[source.url]
            if not reviews:
                continue
            variant = 1 if item.source_key.endswith("#2") else 0
            review = reviews[min(variant, len(reviews) - 1)]
            draft = review.reviewed_draft
            results.append(
                {
                    "page_id": item.page_id,
                    "approved": review.approved,
                    "hook_type": draft.hook_type.value if draft.hook_type else "",
                    "hook_text": draft.hook_text,
                    "blog_link_used": draft.blog_link_used,
                    "issues": review.issues,
                }
            )
            if not dry_run:
                self.queue.replace_draft(
                    item.page_id, source, review, **({"variant": variant} if variant else {})
                )
        return {"candidates": len(items), "updated": 0 if dry_run else len(items), "items": results}

    def schedule_approved(self, now: datetime, slots: tuple[str, ...], timezone: object) -> int:
        items = self.queue.approved_without_schedule()
        if not items:
            return 0
        occupied = self.queue.occupied_schedule_times(now)
        slot_by_type = {
            "재테크팁": "08:30",
            "블로그정보": "12:30",
            "질문형": "16:30",
            "운영글": "21:30",
        }
        items = [item for item in items if item.is_publishable]
        for item in items:
            preferred = item.publish_slot or slot_by_type.get(item.content_type.value, "12:30")
            allowed = (preferred,) if preferred in slots else ("12:30",)
            scheduled_at = next_available_slots(now, occupied, allowed, 1, timezone)[0]
            self.queue.set_schedule(item.page_id, scheduled_at)
            occupied.add(scheduled_at)
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
            due = self.queue.due(now, limit=1)
            result: dict[str, int | str] = {"scheduled": 0, "published": 0, "due": len(due)}
            if due and self.thumbnail_resolver and due[0].thumbnail_status != "미사용":
                try:
                    resolved = self._resolve_cards(due[0], persist=False)
                    result.update({
                        "card_count": len(resolved.card_urls),
                        "card_urls": resolved.card_urls,
                    })
                except ThumbnailError as exc:
                    result.update({"blocked": 1, "thumbnail_error": str(exc)})
            return result  # type: ignore[return-value]

        scheduled = self.schedule_approved(now, slots, timezone)
        due = self.queue.due(now, limit=1)
        if not due:
            return {"scheduled": scheduled, "published": 0, "due": 0}

        item = due[0]
        if not item.is_publishable:   # defence in depth; the queue filter already excludes these
            return {"scheduled": scheduled, "published": 0, "due": 0}
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
        issues = validate_draft_against_source(
            item.draft,
            current_source,
            product,
            allow_two_post_thread=item.thumbnail_status != "미사용",
        )
        if issues:
            message = "게시 직전 검증 실패: " + "; ".join(issues)
            self.queue.fail(item, message)
            raise RuntimeError(message)
        try:
            item = self._resolve_cards(item, persist=True)
        except ThumbnailError as exc:
            if hasattr(self.queue, "hold_thumbnail"):
                self.queue.hold_thumbnail(
                    item.page_id,
                    str(exc),
                    status="누락" if "없습니다" in str(exc) else "검수필요",
                )
            raise RuntimeError(str(exc)) from exc
        if item.thumbnail_status != "미사용":
            posts = item.draft.posts
            if len(posts) < 2 or item.source_url not in posts[1] or posts[0].count(item.source_url):
                message = "썸네일 게시물은 첫 답글에만 블로그 링크가 있어야 합니다."
                if hasattr(self.queue, "hold_thumbnail"):
                    self.queue.hold_thumbnail(item.page_id, message)
                raise RuntimeError(message)
            if posts[1].count(item.source_url) != 1:
                message = "첫 답글의 블로그 링크는 정확히 한 번이어야 합니다."
                if hasattr(self.queue, "hold_thumbnail"):
                    self.queue.hold_thumbnail(item.page_id, message)
                raise RuntimeError(message)
        if not self.queue.claim(item):
            return {"scheduled": scheduled, "published": 0, "due": 0}
        try:
            ids = publisher.publish(
                item,
                save_progress=lambda value: self.queue.save_progress(item.page_id, value),
            )
            verification = publisher.verify_published(ids[0])
            self.queue.complete_verified(
                item.page_id, ids, now, verification["permalink"]
            )
        except Exception as exc:
            if getattr(exc, "retryable", False):
                self.queue.retry(item, str(exc))
            else:
                self.queue.fail(item, str(exc))
            raise
        return {
            "scheduled": scheduled,
            "published": 1,
            "due": 1,
            "checked": 1,
            "blocked": 0,
            "failed": 0,
            "permalink": verification["permalink"],
        }

    def _resolve_cards(self, item, *, persist: bool):
        """Card news is required for items that use media; a missing set holds publishing."""
        if item.thumbnail_status == "미사용":
            return item
        if self.thumbnail_resolver is None:
            raise ThumbnailError("카드뉴스 resolver가 설정되지 않았습니다.")
        if item.card_urls:
            for url in item.card_urls:
                self.thumbnail_resolver.verify(url)
            return item.model_copy(update={"thumbnail_status": "준비"})
        resolution = self.thumbnail_resolver.resolve_cards(item.thumbnail_number)
        resolved = item.model_copy(update={
            "thumbnail_file": "\n".join(resolution.filenames),
            "thumbnail_url": resolution.public_urls[0],
            "card_urls": list(resolution.public_urls),
        })
        if not persist:
            return resolved
        for url in resolution.public_urls:
            self.thumbnail_resolver.verify(url)
        if hasattr(self.queue, "set_cards"):
            self.queue.set_cards(
                item.page_id,
                number=resolution.number,
                filenames=list(resolution.filenames),
                urls=list(resolution.public_urls),
            )
        return resolved.model_copy(update={"thumbnail_status": "준비"})
