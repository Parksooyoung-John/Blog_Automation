from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from sns_harness.models import QueueItem, QueueStatus, ReviewResult, SourcePost, ThreadsDraft
from sns_harness.orchestrator import HarnessOrchestrator


class FakeSource:
    def __init__(self, post: SourcePost) -> None:
        self.post = post

    def discover(self, limit: int = 20) -> list[str]:
        return [self.post.url]

    def fetch(self, url: str) -> SourcePost:
        return self.post


class FakeWriter:
    def __init__(self, draft: ThreadsDraft) -> None:
        self.draft = draft
        self.calls = 0

    def generate(self, source: SourcePost) -> ThreadsDraft:
        self.calls += 1
        return self.draft


class FakeReviewer:
    def review(self, source: SourcePost, draft: ThreadsDraft) -> ReviewResult:
        return ReviewResult(approved=True, reviewed_draft=draft)


class Existing:
    def __init__(self, source_hash: str, status: QueueStatus) -> None:
        self.source_hash = source_hash
        self.status = status
        self.page_id = "page-1"


class FakeQueue:
    def __init__(self, existing: Existing | None = None) -> None:
        self.existing = existing
        self.created = 0
        self.replaced = 0
        self.hash_updates = 0
        self.failed = 0
        self.retried = 0

    def find_by_tistory_id(self, tistory_id: str):
        return self.existing

    def create(self, source, review):
        self.created += 1

    def replace_draft(self, page_id, source, review):
        self.replaced += 1

    def update_source_hash(self, page_id, source_hash):
        self.hash_updates += 1

    def fail(self, item, message):
        self.failed += 1

    def retry(self, item, message):
        self.retried += 1


def make_source(content: str = "12억 원 이하 조건") -> SourcePost:
    return SourcePost(
        tistory_id="165",
        url="https://j2gblog.tistory.com/165",
        title="취득세 감면",
        content=content,
        published_at=datetime.now(UTC) - timedelta(hours=1),
    )


def test_published_source_change_updates_hash_without_regeneration() -> None:
    post = make_source("수정된 12억 원 이하 조건")
    writer = FakeWriter(
        ThreadsDraft(format="single", posts=[f"조건 확인 {post.url}"])
    )
    queue = FakeQueue(Existing("old-hash", QueueStatus.PUBLISHED))
    orchestrator = HarnessOrchestrator(FakeSource(post), writer, FakeReviewer(), queue)

    result = orchestrator.sync(now=datetime.now(UTC))

    assert result["updated"] == 1
    assert queue.hash_updates == 1
    assert writer.calls == 0


def test_unpublished_source_change_regenerates_and_resets_draft() -> None:
    post = make_source("수정된 12억 원 이하 조건")
    draft = ThreadsDraft(format="single", posts=[f"조건 확인 {post.url}"])
    writer = FakeWriter(draft)
    queue = FakeQueue(Existing("old-hash", QueueStatus.APPROVED))
    orchestrator = HarnessOrchestrator(FakeSource(post), writer, FakeReviewer(), queue)

    result = orchestrator.sync(now=datetime.now(UTC))

    assert result["updated"] == 1
    assert queue.replaced == 1
    assert writer.calls == 1


def test_dry_run_has_no_openai_or_queue_writes() -> None:
    post = make_source()
    writer = FakeWriter(ThreadsDraft(format="single", posts=[f"조건 확인 {post.url}"]))
    queue = FakeQueue()
    orchestrator = HarnessOrchestrator(FakeSource(post), writer, FakeReviewer(), queue)

    result = orchestrator.sync(dry_run=True, now=datetime.now(UTC))

    assert result["created"] == 1
    assert writer.calls == 0
    assert queue.created == 0


def test_publish_stops_when_source_changed_after_approval() -> None:
    current_source = make_source("승인 후 바뀐 원문")
    approved = QueueItem(
        page_id="page-1",
        status=QueueStatus.APPROVED,
        source_url=current_source.url,
        tistory_id=current_source.tistory_id,
        source_hash="old-hash",
        title=current_source.title,
        draft=ThreadsDraft(
            format="single",
            posts=[f"조건은 원문에서 확인하세요. {current_source.url}"],
        ),
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    class PublishQueue(FakeQueue):
        def approved_without_schedule(self):
            return []

        def due(self, now, limit=1):
            return [approved]

    class Publisher:
        def publish(self, item, save_progress):
            raise AssertionError("publisher must not be called")

    queue = PublishQueue()
    orchestrator = HarnessOrchestrator(
        FakeSource(current_source), None, None, queue
    )

    with pytest.raises(RuntimeError, match="원문이 승인 후 변경"):
        orchestrator.publish_due(
            Publisher(),
            now=datetime.now(UTC),
            slots=("08:30", "18:30"),
            timezone=ZoneInfo("Asia/Seoul"),
        )

    assert queue.failed == 1


def test_retryable_publish_error_keeps_item_for_retry() -> None:
    current_source = make_source()
    approved = QueueItem(
        page_id="page-1",
        status=QueueStatus.APPROVED,
        source_url=current_source.url,
        tistory_id=current_source.tistory_id,
        source_hash=current_source.source_hash,
        title=current_source.title,
        draft=ThreadsDraft(
            format="single",
            posts=[f"12억 원 이하 조건은 원문을 확인하세요. {current_source.url}"],
        ),
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    class PublishQueue(FakeQueue):
        def approved_without_schedule(self):
            return []

        def due(self, now, limit=1):
            return [approved]

        def claim(self, item):
            return True

    class RetryableError(RuntimeError):
        retryable = True

    class Publisher:
        def publish(self, item, save_progress):
            raise RetryableError("temporary failure")

    queue = PublishQueue()
    orchestrator = HarnessOrchestrator(FakeSource(current_source), None, None, queue)

    with pytest.raises(RetryableError):
        orchestrator.publish_due(
            Publisher(),
            now=datetime.now(UTC),
            slots=("08:30", "18:30"),
            timezone=ZoneInfo("Asia/Seoul"),
        )

    assert queue.retried == 1
    assert queue.failed == 0
