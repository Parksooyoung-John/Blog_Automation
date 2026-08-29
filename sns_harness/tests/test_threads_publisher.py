from datetime import UTC, datetime

from sns_harness.models import QueueItem, QueueStatus, ThreadsDraft
from sns_harness.publishers.threads import ThreadsPublisher


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.created = []
        self.publish_count = 0

    def request(self, method, url, **kwargs):
        if url.endswith("threads_publishing_limit"):
            return FakeResponse({"data": [{"quota_usage": 2, "config": {"quota_total": 250}}]})
        if method == "GET" and url.endswith("/threads"):
            return FakeResponse({"data": []})
        if method == "POST" and url.endswith("/threads"):
            self.created.append(kwargs["data"])
            return FakeResponse({"id": f"container-{len(self.created)}"})
        if url.endswith("threads_publish"):
            self.publish_count += 1
            return FakeResponse({"id": f"media-{self.publish_count}"})
        raise AssertionError((method, url, kwargs))


def item(existing_ids=None) -> QueueItem:
    return QueueItem(
        page_id="page",
        status=QueueStatus.PUBLISHING,
        source_url="https://j2gblog.tistory.com/165",
        tistory_id="165",
        source_hash="hash",
        title="제목",
        draft=ThreadsDraft(
            format="thread",
            posts=[
                "첫 게시물",
                "두 번째 게시물",
                "마지막 https://j2gblog.tistory.com/165",
            ],
            topic_tag="취득세",
        ),
        threads_ids=existing_ids or [],
        scheduled_at=datetime.now(UTC),
    )


def test_publishes_root_then_reply_chain_and_saves_each_id() -> None:
    session = FakeSession()
    publisher = ThreadsPublisher("user", "token", session=session, sleep=lambda _: None)
    progress = []

    result = publisher.publish(item(), lambda ids: progress.append(list(ids)))

    assert result == ["media-1", "media-2", "media-3"]
    assert progress[-1] == result
    assert "reply_to_id" not in session.created[0]
    assert session.created[1]["reply_to_id"] == "media-1"
    assert session.created[2]["reply_to_id"] == "media-2"
    assert session.created[0]["topic_tag"] == "취득세"


def test_resumes_after_existing_root_without_reposting_it() -> None:
    session = FakeSession()
    publisher = ThreadsPublisher("user", "token", session=session, sleep=lambda _: None)

    result = publisher.publish(item(["existing-root"]), lambda _: None)

    assert result == ["existing-root", "media-1", "media-2"]
    assert len(session.created) == 2
    assert session.created[0]["reply_to_id"] == "existing-root"
