from __future__ import annotations

from datetime import UTC, datetime

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


def test_scheduling_and_due_queries_select_only_naver_items() -> None:
    session = RecordingSession()
    queue = NotionQueue("key", "database", session=session)  # type: ignore[arg-type]
    now = datetime.now(UTC)

    assert queue.approved_without_schedule() == []
    assert queue.occupied_schedule_times(now) == set()
    assert queue.due(now) == []

    assert len(session.payloads) == 3
    for payload in session.payloads:
        conditions = payload["filter"]["and"]  # type: ignore[index]
        assert NAVER_SOURCE_FILTER in conditions


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
