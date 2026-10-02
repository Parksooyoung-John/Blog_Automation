from __future__ import annotations

from datetime import UTC, datetime

from sns_harness.models import HookType
from sns_harness.queues.notion import NAVER_SOURCE_FILTER, NotionQueue


class EmptyQueryResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"results": [], "has_more": False}


class RecordingSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.payloads: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
    ) -> EmptyQueryResponse:
        self.payloads.append(json)
        return EmptyQueryResponse()


def test_scheduling_and_due_queries_include_manual_daily_items() -> None:
    session = RecordingSession()
    queue = NotionQueue("key", "database", session=session)  # type: ignore[arg-type]
    now = datetime.now(UTC)

    assert queue.approved_without_schedule() == []
    assert queue.occupied_schedule_times(now) == set()
    assert queue.due(now) == []

    assert len(session.payloads) == 3
    for payload in session.payloads:
        conditions = payload["filter"]["and"]  # type: ignore[index]
        assert NAVER_SOURCE_FILTER not in conditions


def test_sales_draft_query_selects_only_requested_naver_items() -> None:
    session = RecordingSession()
    queue = NotionQueue("key", "database", session=session)  # type: ignore[arg-type]

    assert queue.sales_draft_requests() == []

    conditions = session.payloads[0]["filter"]["and"]  # type: ignore[index]
    assert NAVER_SOURCE_FILTER in conditions
    assert {
        "property": "상태",
        "select": {"equals": "판매초안요청"},
    } in conditions


def test_blog_policy_avoids_last_hook_and_allows_one_link_after_nine_posts(
    monkeypatch,
) -> None:
    queue = NotionQueue("key", "database", session=RecordingSession())  # type: ignore[arg-type]
    pages = [
        {
            "created_time": f"2026-10-0{2 if index < 5 else 1}T00:00:00Z",
            "properties": {
                "Hook유형": {"select": {"name": "궁금증" if index == 0 else "숫자"}},
                "블로그링크사용": {"checkbox": False},
            },
        }
        for index in range(9)
    ]
    monkeypatch.setattr(queue, "_query", lambda *args, **kwargs: pages)

    policy = queue.blog_generation_policy(datetime(2026, 10, 2, tzinfo=UTC))

    assert policy["include_link"] is True
    assert len(policy["hook_types"]) == 3
    assert policy["hook_types"][0] is not HookType.CURIOSITY
