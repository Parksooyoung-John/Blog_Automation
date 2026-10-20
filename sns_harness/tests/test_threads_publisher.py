from datetime import UTC, datetime

import pytest

from sns_harness.models import QueueItem, QueueStatus, ThreadsDraft
from sns_harness.publishers.threads import ThreadsAPIError, ThreadsPublisher


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

    def request(self, method, url, **kwargs):
        if url.endswith("threads_publishing_limit"):
            return FakeResponse({"data": [{"quota_usage": 2, "config": {"quota_total": 250}}]})
        if method == "GET" and url.endswith("/threads"):
            return FakeResponse({"data": []})
        if method == "POST" and url.endswith("/threads"):
            self.created.append(kwargs["data"])
            return FakeResponse({"id": f"container-{len(self.created)}"})
        if method == "POST" and url.endswith("/threads_publish"):
            return FakeResponse({"id": f"media-{len(self.created)}"})
        if method == "GET" and "/container-" in url:
            return FakeResponse({"status": "FINISHED"})
        raise AssertionError((method, url, kwargs))


class SlowContainerSession(FakeSession):
    """Containers stay IN_PROGRESS for a while; publishing early is the 2026-10-20 400."""

    def __init__(self, in_progress_polls=2, missing_polls=0) -> None:
        super().__init__()
        self.log, self.polls, self.finished = [], {}, set()
        self.in_progress_polls, self.missing_polls = in_progress_polls, missing_polls

    def request(self, method, url, **kwargs):
        if method == "GET" and "/container-" in url:
            container = url.rsplit("/", 1)[1]
            n = self.polls[container] = self.polls.get(container, 0) + 1
            self.log.append("poll")
            if n <= self.missing_polls:
                missing = {"error": {"message": "The requested resource does not exist"}}
                return FakeResponse(missing, 400)
            done = n > self.missing_polls + self.in_progress_polls
            if done:
                self.finished.add(container)
            return FakeResponse({"status": "FINISHED" if done else "IN_PROGRESS"})
        if method == "POST" and url.endswith("/threads_publish"):
            container = kwargs["data"]["creation_id"]
            assert container in self.finished, f"{container} published before FINISHED"
            self.log.append("publish")
        return super().request(method, url, **kwargs)


def test_every_container_is_ready_before_it_is_published() -> None:
    session = SlowContainerSession(in_progress_polls=2)
    publisher = ThreadsPublisher("user", "token", session=session, sleep=lambda _: None)
    publisher.publish(item(), lambda _: None)
    assert session.log.count("publish") == 3
    assert session.log[:4] == ["poll", "poll", "poll", "publish"]   # 2 IN_PROGRESS, then FINISHED


def test_a_container_that_is_briefly_unreadable_is_waited_for() -> None:
    session = SlowContainerSession(in_progress_polls=0, missing_polls=2)
    ThreadsPublisher("user", "token", session=session, sleep=lambda _: None).publish(
        item(), lambda _: None
    )
    assert session.log.count("publish") == 3


def test_verifies_permalink_and_expected_username() -> None:
    class VerificationSession(FakeSession):
        def request(self, method, url, **kwargs):
            if method == "GET" and url.endswith("/media-1"):
                return FakeResponse({
                    "id": "media-1",
                    "permalink": "https://www.threads.com/@mone.ybrief/post/example",
                    "username": "mone.ybrief",
                })
            return super().request(method, url, **kwargs)

    publisher = ThreadsPublisher("user", "token", session=VerificationSession())
    result = publisher.verify_published("media-1")
    assert result["username"] == "mone.ybrief"


def test_rejects_post_published_to_unexpected_username() -> None:
    class WrongAccountSession(FakeSession):
        def request(self, method, url, **kwargs):
            return FakeResponse({
                "id": "media-1",
                "permalink": "https://www.threads.com/@wrong/post/example",
                "username": "wrong",
            })

    publisher = ThreadsPublisher("user", "token", session=WrongAccountSession())
    with pytest.raises(
        ThreadsAPIError,
        match="actual='wrong', expected='mone.ybrief'",
    ):
        publisher.verify_published("media-1")


def test_collects_official_post_insights() -> None:
    class InsightsSession(FakeSession):
        def request(self, method, url, **kwargs):
            if method == "GET" and url.endswith("/media-1/insights"):
                assert kwargs["params"]["metric"] == "views,likes,replies,reposts,quotes,shares"
                return FakeResponse(
                    {
                        "data": [
                            {"name": "views", "values": [{"value": 120}]},
                            {"name": "likes", "values": [{"value": 8}]},
                            {"name": "replies", "values": [{"value": 3}]},
                            {"name": "reposts", "values": [{"value": 2}]},
                            {"name": "quotes", "values": [{"value": 1}]},
                            {"name": "shares", "values": [{"value": 4}]},
                        ]
                    }
                )
            return super().request(method, url, **kwargs)

    metrics = ThreadsPublisher("user", "token", session=InsightsSession()).post_insights(
        "media-1", window="24h"
    )

    assert metrics.views == 120
    assert metrics.likes == 8
    assert metrics.quotes_shares == 5
    assert metrics.source == "Threads Insights API"


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
    assert all("auto_publish_text" not in row for row in session.created)


def test_publishes_thumbnail_only_on_root_post() -> None:
    session = FakeSession()
    draft_item = item()
    draft_item = draft_item.model_copy(update={
        "thumbnail_status": "준비",
        "thumbnail_url": "https://raw.githubusercontent.com/owner/repo/main/17.png",
    })
    ThreadsPublisher("user", "token", session=session, sleep=lambda _: None).publish(
        draft_item, lambda _: None
    )
    assert session.created[0]["media_type"] == "IMAGE"
    assert session.created[0]["image_url"].endswith("17.png")
    assert all(row["media_type"] == "TEXT" for row in session.created[1:])


def test_resumes_after_existing_root_without_reposting_it() -> None:
    session = FakeSession()
    publisher = ThreadsPublisher("user", "token", session=session, sleep=lambda _: None)

    result = publisher.publish(item(["existing-root"]), lambda _: None)

    assert result == ["existing-root", "media-1", "media-2"]
    assert len(session.created) == 2
    assert session.created[0]["reply_to_id"] == "existing-root"


def test_auto_publish_error_is_terminal() -> None:
    class ErrorSession(FakeSession):
        def request(self, method, url, **kwargs):
            if method == "POST" and url.endswith("/threads"):
                return FakeResponse({"error": {"message": "invalid topic"}}, status_code=400)
            return super().request(method, url, **kwargs)

    session = ErrorSession()
    publisher = ThreadsPublisher("user", "token", session=session, sleep=lambda _: None)

    with pytest.raises(ThreadsAPIError, match="invalid topic") as raised:
        publisher.publish(item(), lambda _: None)

    assert raised.value.retryable is False
