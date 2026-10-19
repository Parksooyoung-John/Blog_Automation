from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sns_harness.models import QueueItem, QueueStatus, SourcePost, ThreadsDraft
from sns_harness.orchestrator import HarnessOrchestrator
from sns_harness.publishers.threads import ThreadsAPIError, ThreadsPublisher
from sns_harness.thumbnails import CardNewsResolution, ThumbnailError, resolve_card_news


def touch(directory: Path, *names: str) -> None:
    for name in names:
        (directory / name).write_bytes(b"png")


def test_cards_resolve_in_slide_order_and_ignore_other_posts(tmp_path: Path) -> None:
    touch(tmp_path, "18_카드뉴스_2.png", "18_카드뉴스_1.png", "18_카드뉴스_3.jpg",
          "1_카드뉴스_1.png", "180_카드뉴스_1.png", "18_썸네일.png")
    result = resolve_card_news(18, tmp_path)
    assert result.filenames == ("18_카드뉴스_1.png", "18_카드뉴스_2.png", "18_카드뉴스_3.jpg")


def test_missing_cards_say_missing(tmp_path: Path) -> None:
    touch(tmp_path, "18_썸네일.png")
    with pytest.raises(ThumbnailError, match="없습니다"):
        resolve_card_news(18, tmp_path)


@pytest.mark.parametrize("names", [
    ("18_카드뉴스_1.png",),                                 # one slide is not a carousel
    ("18_카드뉴스_1.png", "18_카드뉴스_3.png"),             # gap
    ("18_카드뉴스_1.png", "18_카드뉴스_1.jpg"),             # duplicate slide number
])
def test_incomplete_card_sets_are_rejected(tmp_path: Path, names) -> None:
    touch(tmp_path, *names)
    with pytest.raises(ThumbnailError) as raised:
        resolve_card_news(18, tmp_path)
    assert "없습니다" not in str(raised.value)   # must map to 검수필요, not 누락


def test_oversized_card_is_rejected(tmp_path: Path) -> None:
    touch(tmp_path, "18_카드뉴스_1.png")
    (tmp_path / "18_카드뉴스_2.png").write_bytes(bytes(8 * 1024 * 1024 + 1))
    with pytest.raises(ThumbnailError, match="8MB"):
        resolve_card_news(18, tmp_path)


class Response:
    def __init__(self, payload, status_code=200) -> None:
        self.payload, self.status_code, self.headers, self.text = payload, status_code, {}, "x"

    def json(self):
        return self.payload


class CarouselSession:
    def __init__(self, statuses=("FINISHED",)) -> None:
        self.created, self.polls, self.statuses = [], 0, list(statuses)

    def request(self, method, url, **kwargs):
        if url.endswith("threads_publishing_limit"):
            return Response({"data": [{"quota_usage": 0, "config": {"quota_total": 250}}]})
        if method == "GET" and url.endswith("/threads"):
            return Response({"data": []})
        if method == "GET":
            self.polls += 1
            state = self.statuses[min(self.polls - 1, len(self.statuses) - 1)]
            return Response({"status": state, "error_message": "bad image"})
        if method == "POST" and url.endswith("/threads"):
            self.created.append(kwargs["data"])
            return Response({"id": f"container-{len(self.created)}"})
        if method == "POST" and url.endswith("/threads_publish"):
            return Response({"id": f"media-{len(self.created)}"})
        raise AssertionError((method, url))


def carousel_item() -> QueueItem:
    return QueueItem(
        page_id="page", status=QueueStatus.PUBLISHING, source_url="https://blog/18",
        tistory_id="18", source_hash="h", title="제목",
        draft=ThreadsDraft(format="thread", posts=["훅 한 줄", "링크 https://blog/18"]),
        scheduled_at=datetime.now(UTC), thumbnail_status="준비",
        thumbnail_url="https://raw/18_카드뉴스_1.png",
        card_urls=["https://raw/18_카드뉴스_1.png", "https://raw/18_카드뉴스_2.png"],
    )


def test_carousel_children_then_carousel_then_text_reply() -> None:
    session = CarouselSession()
    ids = ThreadsPublisher("u", "t", session=session, sleep=lambda _: None).publish(
        carousel_item(), lambda _: None
    )
    assert ids == ["media-3", "media-4"]
    children, carousel, reply = session.created[:2], session.created[2], session.created[3]
    assert all(c["is_carousel_item"] == "true" and c["media_type"] == "IMAGE" for c in children)
    assert carousel["media_type"] == "CAROUSEL"
    assert carousel["children"] == "container-1,container-2"
    assert "reply_to_id" not in carousel and carousel["text"] == "훅 한 줄"
    assert reply["media_type"] == "TEXT" and reply["reply_to_id"] == "media-3"


def test_container_error_stops_before_publishing() -> None:
    session = CarouselSession(statuses=("ERROR",))
    with pytest.raises(ThreadsAPIError, match="bad image"):
        ThreadsPublisher("u", "t", session=session, sleep=lambda _: None).publish(
            carousel_item(), lambda _: None
        )
    assert len(session.created) == 1   # nothing past the first child, nothing published


def test_container_that_never_finishes_is_retryable() -> None:
    session = CarouselSession(statuses=("IN_PROGRESS",))
    with pytest.raises(ThreadsAPIError) as raised:
        ThreadsPublisher("u", "t", session=session, sleep=lambda _: None).publish(
            carousel_item(), lambda _: None
        )
    assert raised.value.retryable is True


class Source:
    def __init__(self, post: SourcePost) -> None:
        self.post = post

    def fetch(self, url: str) -> SourcePost:
        return self.post


class Queue:
    def __init__(self, item: QueueItem) -> None:
        self.item, self.held, self.cards = item, None, None

    def approved_without_schedule(self):
        return []

    def due(self, now, limit=1):
        return [self.item]

    def claim(self, item):
        return True

    def hold_thumbnail(self, page_id, message, *, status="검수필요"):
        self.held = (status, message)

    def set_cards(self, page_id, **kwargs):
        self.cards = kwargs

    def save_progress(self, page_id, ids):
        pass

    def complete_verified(self, *args):
        pass


def due_item(post: SourcePost, **update) -> QueueItem:
    return QueueItem(
        page_id="page", status=QueueStatus.APPROVED, source_url=post.url,
        tistory_id=post.tistory_id, source_hash=post.source_hash, title=post.title,
        draft=ThreadsDraft(format="thread", posts=[
            "취득세 감면 12억 원 이하 조건", f"원문은 여기에서 확인하세요. {post.url}",
        ]),
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        thumbnail_number=18, thumbnail_status="번호필요", **update,
    )


def source() -> SourcePost:
    return SourcePost(
        tistory_id="165", url="https://j2gblog.tistory.com/165", title="취득세 감면",
        content="12억 원 이하 조건", published_at=datetime.now(UTC) - timedelta(hours=1),
    )


def run_publish(queue, resolver, publisher):
    return HarnessOrchestrator(Source(source()), None, None, queue, resolver).publish_due(
        publisher, now=datetime.now(UTC), slots=("12:30",), timezone=ZoneInfo("Asia/Seoul"),
    )


def test_publishing_is_held_when_no_card_news_exists() -> None:
    class Resolver:
        def resolve_cards(self, number):
            raise ThumbnailError("게시번호 18에 맞는 카드뉴스가 없습니다.")

    class Publisher:
        def publish(self, *args):
            raise AssertionError("must not publish without cards")

    queue = Queue(due_item(source()))
    with pytest.raises(RuntimeError, match="카드뉴스가 없습니다"):
        run_publish(queue, Resolver(), Publisher())
    assert queue.held[0] == "누락"


def test_publishing_passes_resolved_cards_to_publisher() -> None:
    urls = ("https://raw/18_카드뉴스_1.png", "https://raw/18_카드뉴스_2.png")

    class Resolver:
        def resolve_cards(self, number):
            return CardNewsResolution(18, ("18_카드뉴스_1.png", "18_카드뉴스_2.png"), (), urls)

        def verify(self, url):
            pass

    seen = {}

    class Publisher:
        def publish(self, item, save_progress):
            seen["item"] = item
            return ["media-1", "media-2"]

        def verify_published(self, media_id):
            return {"permalink": "https://threads/p"}

    queue = Queue(due_item(source()))
    run_publish(queue, Resolver(), Publisher())
    assert seen["item"].card_urls == list(urls)
    assert seen["item"].thumbnail_status == "준비"
    assert queue.cards["urls"] == list(urls) and queue.cards["number"] == 18
