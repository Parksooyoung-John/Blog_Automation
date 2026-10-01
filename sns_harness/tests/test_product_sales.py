from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from sns_harness.agents.writer import ThreadsWriter
from sns_harness.models import (
    ProductDraftContent,
    ProductOffer,
    QueueItem,
    QueueStatus,
    ReviewResult,
    SourcePost,
    ThreadsDraft,
    validate_draft_against_source,
)
from sns_harness.orchestrator import HarnessOrchestrator


def source() -> SourcePost:
    return SourcePost(
        source="naver",
        source_id="123",
        url="https://blog.naver.com/education_blog/123",
        title="생활비 기록 방법",
        content="생활비는 항목별로 기록하고 매달 확인합니다.",
        published_at=datetime.now(UTC) - timedelta(hours=1),
    )


def product() -> ProductOffer:
    return ProductOffer(
        platform="쿠팡파트너스",
        name="가계부",
        url="https://link.coupang.com/a/example",
        recommendation_basis="생활비 항목을 직접 기록할 수 있는 종이 가계부",
    )


def product_item(**updates: object) -> QueueItem:
    values = {
        "page_id": "page-1",
        "status": QueueStatus.SALES_DRAFT_REQUESTED,
        "source_url": source().url,
        "source_key": source().source_key,
        "source_hash": source().source_hash,
        "title": source().title,
        "draft": ThreadsDraft(format="single", posts=[f"생활비 기록 {source().url}"]),
        "product_platform": product().platform.value,
        "product_name": product().name,
        "product_url": product().url,
        "recommendation_basis": product().recommendation_basis,
    }
    values.update(updates)
    return QueueItem(**values)


def test_writer_composes_required_product_layout() -> None:
    content = ProductDraftContent(
        information_posts=["생활비를 항목별로 기록하세요."],
        sales_copy="종이에 직접 정리하고 싶을 때 참고할 수 있습니다.",
        topic_tag="생활비",
    )

    draft = ThreadsWriter._compose_product_draft(source(), product(), content)

    assert len(draft.posts) == 2
    assert draft.posts[0].startswith("[광고 포함]\n")
    assert draft.posts[0].endswith(source().url)
    assert draft.posts[-1].startswith(product().effective_disclosure)
    assert draft.posts[-1].endswith(product().url)


def test_product_draft_rejects_price_claim_in_sales_reply() -> None:
    offer = product()
    draft = ThreadsDraft(
        format="thread",
        posts=[
            f"[광고 포함]\n생활비 기록 방법입니다.\n{source().url}",
            f"{offer.effective_disclosure}\n지금 9,900원입니다.\n{offer.url}",
        ],
    )

    issues = validate_draft_against_source(draft, source(), offer)

    assert "sales reply must not contain price or discount claims" in issues


def test_prepare_sales_resets_to_reviewable_draft() -> None:
    item = product_item(scheduled_at=datetime.now(UTC))
    generated = ThreadsWriter._compose_product_draft(
        source(),
        product(),
        ProductDraftContent(information_posts=["생활비를 기록하세요."], sales_copy="참고하세요."),
    )

    class Source:
        def fetch(self, url: str) -> SourcePost:
            return source()

    class Writer:
        def generate_for_product(self, source_post, offer, existing_draft):
            return generated

    class Reviewer:
        def review(self, source_post, draft, offer):
            return ReviewResult(approved=True, reviewed_draft=draft)

    class Queue:
        replacement = None

        def sales_draft_requests(self):
            return [item]

        def replace_sales_draft(self, page_id, source_post, review, product_hash):
            self.replacement = (page_id, review, product_hash)

    queue = Queue()
    result = HarnessOrchestrator(Source(), Writer(), Reviewer(), queue).prepare_sales()

    assert result == {"candidates": 1, "prepared": 1, "held": 0, "skipped": 0}
    assert queue.replacement[0] == "page-1"
    assert queue.replacement[2] == product().product_hash


def test_prepare_sales_dry_run_does_not_use_openai_or_write() -> None:
    item = product_item()

    class Queue:
        def sales_draft_requests(self):
            return [item]

    class Source:
        def fetch(self, url):
            raise AssertionError("dry-run must not fetch or generate content")

    result = HarnessOrchestrator(Source(), None, None, Queue()).prepare_sales(dry_run=True)

    assert result == {"candidates": 1, "prepared": 1, "held": 0, "skipped": 0}


def test_prepare_sales_holds_incomplete_product_input() -> None:
    item = product_item(product_url="")

    class Queue:
        held = None

        def sales_draft_requests(self):
            return [item]

        def hold_sales_request(self, page_id, message):
            self.held = (page_id, message)

    queue = Queue()
    result = HarnessOrchestrator(object(), object(), object(), queue).prepare_sales()

    assert result == {"candidates": 1, "prepared": 0, "held": 1, "skipped": 0}
    assert queue.held[0] == "page-1"
    assert "상품 정보 검증 실패" in queue.held[1]


def test_publish_rejects_product_changed_after_approval() -> None:
    item = product_item(
        status=QueueStatus.APPROVED,
        product_hash="old-hash",
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    class Source:
        def fetch(self, url):
            return source()

    class Queue:
        failed = 0

        def approved_without_schedule(self):
            return []

        def due(self, now, limit=1):
            return [item]

        def fail(self, queue_item, message):
            self.failed += 1

    class Publisher:
        def publish(self, item, save_progress):
            raise AssertionError("changed product must not be published")

    queue = Queue()
    orchestrator = HarnessOrchestrator(Source(), None, None, queue)

    with pytest.raises(RuntimeError, match="상품 정보가 승인 후 변경"):
        orchestrator.publish_due(
            Publisher(),
            now=datetime.now(UTC),
            slots=("08:30", "18:30"),
            timezone=ZoneInfo("Asia/Seoul"),
        )

    assert queue.failed == 1


def test_prepare_sales_skips_already_published_item() -> None:
    item = product_item(
        published_at=datetime.now(UTC),
        threads_ids=["thread-1"],
    )
    queue = SimpleNamespace(sales_draft_requests=lambda: [item])

    result = HarnessOrchestrator(object(), None, None, queue).prepare_sales(dry_run=True)

    assert result == {"candidates": 1, "prepared": 0, "held": 0, "skipped": 1}


def test_source_change_regenerates_existing_product_draft() -> None:
    current_source = source().model_copy(update={"content": "생활비 기록 기준이 수정됐습니다."})
    item = product_item(status=QueueStatus.APPROVED, source_hash="old-hash")
    generated = ThreadsWriter._compose_product_draft(
        current_source,
        product(),
        ProductDraftContent(information_posts=["수정된 기준입니다."], sales_copy="참고하세요."),
    )

    class Source:
        def discover(self, limit=20):
            return [current_source.url]

        def fetch(self, url):
            return current_source

    class Writer:
        def generate_for_product(self, source_post, offer, existing_draft):
            return generated

    class Reviewer:
        def review(self, source_post, draft, offer):
            return ReviewResult(approved=True, reviewed_draft=draft)

    class Queue:
        replacement = None

        def find_by_source_key(self, source_key):
            return item

        def replace_sales_draft(self, page_id, source_post, review, product_hash):
            self.replacement = (page_id, source_post, review, product_hash)

    queue = Queue()
    result = HarnessOrchestrator(Source(), Writer(), Reviewer(), queue).sync(
        backfill=1,
        now=datetime.now(UTC),
    )

    assert result["updated"] == 1
    assert queue.replacement[1] == current_source
    assert queue.replacement[3] == product().product_hash
