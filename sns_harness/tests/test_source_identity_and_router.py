from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sns_harness.models import (
    QueueItem,
    QueueStatus,
    SourceKind,
    SourcePost,
    ThreadsDraft,
)
from sns_harness.queues.notion import NotionQueue
from sns_harness.sources.router import PublishSourceRouter


def make_post(source: SourceKind, source_id: str, url: str) -> SourcePost:
    return SourcePost(
        source=source,
        source_id=source_id,
        url=url,
        title="제목",
        content="본문",
        published_at=datetime.now(UTC),
    )


def test_source_keys_are_compatible_and_do_not_collide() -> None:
    tistory = SourcePost(
        tistory_id="165",
        url="https://j2gblog.tistory.com/165",
        title="티스토리",
        content="본문",
        published_at=datetime.now(UTC),
    )
    naver = make_post(
        SourceKind.NAVER,
        "165",
        "https://blog.naver.com/education_blog/165",
    )

    assert tistory.source is SourceKind.TISTORY
    assert tistory.source_id == "165"
    assert tistory.tistory_id == "165"
    assert tistory.source_key == "165"
    assert naver.source_key == "naver:165"

    item = QueueItem(
        page_id="page",
        status=QueueStatus.DRAFT,
        source_url=tistory.url,
        tistory_id="165",
        source_hash=tistory.source_hash,
        title=tistory.title,
        draft=ThreadsDraft(format="single", posts=[f"본문 {tistory.url}"]),
    )
    assert item.source_key == "165"
    assert item.tistory_id == "165"


def test_notion_legacy_tistory_id_property_stores_namespaced_naver_key() -> None:
    post = make_post(
        SourceKind.NAVER,
        "165",
        "https://blog.naver.com/education_blog/165",
    )
    draft = ThreadsDraft(format="single", posts=[f"본문 {post.url}"])
    properties = NotionQueue("key", "db")._draft_properties(
        post,
        draft,
        QueueStatus.DRAFT,
    )

    assert properties["TistoryID"]["rich_text"][0]["text"]["content"] == "naver:165"


class FakeSource:
    def __init__(self, base_url: str, post: SourcePost) -> None:
        self.base_url = base_url
        self.post = post
        self.calls: list[str] = []

    def fetch(self, url: str) -> SourcePost:
        self.calls.append(url)
        return self.post


def test_publish_source_router_dispatches_by_host() -> None:
    tistory_post = make_post(
        SourceKind.TISTORY, "1", "https://j2gblog.tistory.com/1"
    )
    naver_post = make_post(
        SourceKind.NAVER, "2", "https://blog.naver.com/education_blog/2"
    )
    tistory = FakeSource("https://j2gblog.tistory.com", tistory_post)
    naver = FakeSource("https://blog.naver.com/education_blog", naver_post)
    router = PublishSourceRouter(tistory, naver)  # type: ignore[arg-type]

    assert router.fetch(tistory_post.url) is tistory_post
    assert router.fetch(naver_post.url) is naver_post
    assert tistory.calls == [tistory_post.url]
    assert naver.calls == [naver_post.url]

    with pytest.raises(ValueError, match="unsupported source URL"):
        router.fetch("https://example.com/post/1")
