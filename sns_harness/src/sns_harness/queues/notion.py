from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from sns_harness.models import (
    PostFormat,
    QueueItem,
    QueueStatus,
    ReviewResult,
    SourcePost,
    ThreadsDraft,
    threads_ids_from_text,
    threads_ids_to_text,
)

PROPERTY_TYPES = {
    "이름": "title",
    "상태": "select",
    "원문URL": "url",
    "TistoryID": "rich_text",
    "원문발행일": "date",
    "원문해시": "rich_text",
    "형식": "select",
    "첫게시물": "rich_text",
    "답글1": "rich_text",
    "답글2": "rich_text",
    "답글3": "rich_text",
    "답글4": "rich_text",
    "주제태그": "rich_text",
    "예약시각": "date",
    "게시시각": "date",
    "ThreadsIDs": "rich_text",
    "오류": "rich_text",
    "재시도횟수": "number",
    "판매플랫폼": "select",
    "상품명": "rich_text",
    "상품URL": "url",
    "추천근거": "rich_text",
    "광고고지": "rich_text",
    "상품해시": "rich_text",
}

DAILY_PROPERTY_DEFINITIONS = {
    "콘텐츠유형": {
        "select": {"options": [{"name": n} for n in ("블로그정보", "재테크팁", "질문형", "운영글")]}
    },
    "게시슬롯": {"rich_text": {}},
    "원문키": {"rich_text": {}},
    "주제": {"rich_text": {}},
    "Hook유형": {
        "select": {
            "options": [
                {"name": n}
                for n in ("궁금증", "숫자", "실수", "비교", "질문", "경험/공감")
            ]
        }
    },
    "블로그링크사용": {"checkbox": {}},
    "운영메모": {"rich_text": {}},
    "자동생성여부": {"checkbox": {}},
    "사람수정필요": {"checkbox": {}},
    "중복검사키": {"rich_text": {}},
    "성과판정": {
        "select": {
            "options": [
                {"name": n}
                for n in (
                    "미측정",
                    "reach-only",
                    "conversion-candidate",
                    "underperforming",
                    "repeatable",
                )
            ]
        }
    },
}

NAVER_SOURCE_FILTER = {
    "property": "TistoryID",
    "rich_text": {"starts_with": "naver:"},
}


class NotionQueue:
    def __init__(
        self,
        api_key: str,
        database_id: str,
        *,
        timeout: float = 20,
        session: requests.Session | None = None,
    ) -> None:
        self.database_id = database_id
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }
        )
        self.base_url = "https://api.notion.com/v1"

    def validate_schema(self) -> list[str]:
        response = self.session.get(
            f"{self.base_url}/databases/{self.database_id}", timeout=self.timeout
        )
        response.raise_for_status()
        actual = response.json().get("properties", {})
        errors = []
        for name, expected_type in PROPERTY_TYPES.items():
            if name not in actual:
                errors.append(f"missing Notion property: {name}")
            elif actual[name].get("type") != expected_type:
                errors.append(
                    f"Notion property {name!r} must be {expected_type}, "
                    f"got {actual[name].get('type')}"
                )
        return errors

    def ensure_daily_schema(self) -> list[str]:
        response = self.session.get(
            f"{self.base_url}/databases/{self.database_id}", timeout=self.timeout
        )
        response.raise_for_status()
        actual = response.json().get("properties", {})
        missing = {
            name: definition
            for name, definition in DAILY_PROPERTY_DEFINITIONS.items()
            if name not in actual
        }
        if missing:
            response = self.session.patch(
                f"{self.base_url}/databases/{self.database_id}",
                json={"properties": missing},
                timeout=self.timeout,
            )
            response.raise_for_status()
        return sorted(missing)

    def find_by_source_key(self, source_key: str) -> QueueItem | None:
        pages = self._query(
            {"property": "TistoryID", "rich_text": {"equals": source_key}}, page_size=1
        )
        return self._to_item(pages[0]) if pages else None

    def find_by_tistory_id(self, tistory_id: str) -> QueueItem | None:
        """Compatibility wrapper for the legacy Tistory-only interface."""
        return self.find_by_source_key(tistory_id)

    def sales_draft_requests(self) -> list[QueueItem]:
        pages = self._query(
            {
                "and": [
                    {
                        "property": "상태",
                        "select": {"equals": QueueStatus.SALES_DRAFT_REQUESTED.value},
                    },
                    NAVER_SOURCE_FILTER,
                ]
            },
            sorts=[{"timestamp": "last_edited_time", "direction": "ascending"}],
        )
        return [self._to_item(page) for page in pages]

    def create(self, source: SourcePost, review: ReviewResult) -> QueueItem:
        status = QueueStatus.DRAFT if review.approved else QueueStatus.HOLD
        properties = self._draft_properties(source, review.reviewed_draft, status)
        if review.issues:
            properties["오류"] = self._rich("; ".join(review.issues))
        response = self.session.post(
            f"{self.base_url}/pages",
            json={"parent": {"database_id": self.database_id}, "properties": properties},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._to_item(response.json())

    def create_daily_candidate(self, *, title: str, text: str, content_type: str,
                               publish_slot: str, topic: str = "", hook_type: str = "",
                               operator_note: str = "") -> QueueItem:
        properties = {
            "이름": self._title(title), "상태": self._select(QueueStatus.DRAFT.value),
            "원문URL": {"url": None}, "TistoryID": self._rich(""),
            "형식": self._select(PostFormat.SINGLE.value), "첫게시물": self._rich(text),
            "주제태그": self._rich(topic), "ThreadsIDs": self._rich("[]"),
            "오류": self._rich(""), "재시도횟수": {"number": 0},
            "콘텐츠유형": self._select(content_type), "게시슬롯": self._rich(publish_slot),
            "원문키": self._rich(""), "주제": self._rich(topic),
            "블로그링크사용": {"checkbox": False}, "운영메모": self._rich(operator_note),
            "자동생성여부": {"checkbox": True},
            "사람수정필요": {"checkbox": content_type == "운영글"},
            "중복검사키": self._rich(f"{content_type}:{topic}:{text[:80]}"),
            "성과판정": self._select("미측정"),
        }
        if hook_type:
            properties["Hook유형"] = self._select(hook_type)
        response = self.session.post(f"{self.base_url}/pages",
            json={"parent": {"database_id": self.database_id}, "properties": properties},
            timeout=self.timeout)
        response.raise_for_status()
        return self._to_item(response.json())

    def replace_draft(self, page_id: str, source: SourcePost, review: ReviewResult) -> None:
        status = QueueStatus.DRAFT if review.approved else QueueStatus.HOLD
        properties = self._draft_properties(source, review.reviewed_draft, status)
        properties["오류"] = self._rich("; ".join(review.issues))
        properties["예약시각"] = {"date": None}
        self._patch(page_id, properties)

    def replace_sales_draft(
        self,
        page_id: str,
        source: SourcePost,
        review: ReviewResult,
        product_hash: str,
    ) -> None:
        status = QueueStatus.DRAFT if review.approved else QueueStatus.HOLD
        properties = self._draft_properties(source, review.reviewed_draft, status)
        properties.update(
            {
                "오류": self._rich("; ".join(review.issues)),
                "예약시각": {"date": None},
                "상품해시": self._rich(product_hash),
            }
        )
        self._patch(page_id, properties)

    def hold_sales_request(self, page_id: str, message: str) -> None:
        self._patch(
            page_id,
            {
                "상태": self._select(QueueStatus.HOLD.value),
                "예약시각": {"date": None},
                "오류": self._rich(message[:1900]),
            },
        )

    def update_source_hash(self, page_id: str, source_hash: str) -> None:
        self._patch(page_id, {"원문해시": self._rich(source_hash)})

    def approved_without_schedule(self) -> list[QueueItem]:
        pages = self._query(
            {
                "and": [
                    {"property": "상태", "select": {"equals": QueueStatus.APPROVED.value}},
                    {"property": "예약시각", "date": {"is_empty": True}},
                ]
            },
            sorts=[{"timestamp": "created_time", "direction": "ascending"}],
        )
        return [self._to_item(page) for page in pages]

    def occupied_schedule_times(self, after: datetime) -> set[datetime]:
        pages = self._query(
            {
                "and": [
                    {"property": "예약시각", "date": {"on_or_after": after.isoformat()}},
                ]
            },
        )
        result: set[datetime] = set()
        for page in pages:
            date_value = page.get("properties", {}).get("예약시각", {}).get("date")
            if date_value and date_value.get("start"):
                result.add(datetime.fromisoformat(date_value["start"].replace("Z", "+00:00")))
        return result

    def set_schedule(self, page_id: str, scheduled_at: datetime) -> None:
        self._patch(page_id, {"예약시각": {"date": {"start": scheduled_at.isoformat()}}})

    def due(self, now: datetime, limit: int = 1) -> list[QueueItem]:
        pages = self._query(
            {
                "and": [
                    {
                        "or": [
                            {
                                "property": "상태",
                                "select": {"equals": QueueStatus.APPROVED.value},
                            },
                            {
                                "property": "상태",
                                "select": {"equals": QueueStatus.PUBLISHING.value},
                            },
                        ]
                    },
                    {"property": "예약시각", "date": {"on_or_before": now.isoformat()}},
                ]
            },
            sorts=[{"property": "예약시각", "direction": "ascending"}],
            page_size=limit,
        )
        return [self._to_item(page) for page in pages[:limit]]

    def claim(self, item: QueueItem) -> bool:
        if not item.source_key:
            self._patch(item.page_id, {"상태": self._select(QueueStatus.PUBLISHING.value)})
            return True
        current = self.find_by_source_key(item.source_key)
        if not current:
            return False
        if current.status is QueueStatus.PUBLISHING:
            return True
        if current.status is not QueueStatus.APPROVED:
            return False
        self._patch(item.page_id, {"상태": self._select(QueueStatus.PUBLISHING.value)})
        return True

    def save_progress(self, page_id: str, threads_ids: list[str]) -> None:
        self._patch(page_id, {"ThreadsIDs": self._rich(threads_ids_to_text(threads_ids))})

    def complete(self, page_id: str, threads_ids: list[str], published_at: datetime) -> None:
        self._patch(
            page_id,
            {
                "상태": self._select(QueueStatus.PUBLISHED.value),
                "ThreadsIDs": self._rich(threads_ids_to_text(threads_ids)),
                "게시시각": {"date": {"start": published_at.isoformat()}},
                "오류": self._rich(""),
            },
        )

    def fail(self, item: QueueItem, message: str) -> None:
        self._patch(
            item.page_id,
            {
                "상태": self._select(QueueStatus.ERROR.value),
                "오류": self._rich(message[:1900]),
                "예약시각": {"date": None},
                "재시도횟수": {"number": item.retry_count + 1},
            },
        )

    def retry(self, item: QueueItem, message: str) -> None:
        self._patch(
            item.page_id,
            {
                "상태": self._select(QueueStatus.PUBLISHING.value),
                "오류": self._rich(message[:1900]),
                "재시도횟수": {"number": item.retry_count + 1},
            },
        )

    def _draft_properties(
        self, source: SourcePost, draft: ThreadsDraft, status: QueueStatus
    ) -> dict[str, Any]:
        post_values = draft.posts + [""] * (5 - len(draft.posts))
        return {
            "이름": self._title(source.title),
            "상태": self._select(status.value),
            "원문URL": {"url": source.url},
            "TistoryID": self._rich(source.source_key),
            "원문발행일": {"date": {"start": source.published_at.isoformat()}},
            "원문해시": self._rich(source.source_hash),
            "형식": self._select(draft.format.value),
            "첫게시물": self._rich(post_values[0]),
            "답글1": self._rich(post_values[1]),
            "답글2": self._rich(post_values[2]),
            "답글3": self._rich(post_values[3]),
            "답글4": self._rich(post_values[4]),
            "주제태그": self._rich(draft.topic_tag or ""),
            "ThreadsIDs": self._rich("[]"),
            "오류": self._rich(""),
            "재시도횟수": {"number": 0},
        }

    def _query(
        self,
        filter_value: dict[str, Any],
        *,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            payload: dict[str, Any] = {"filter": filter_value, "page_size": page_size}
            if sorts:
                payload["sorts"] = sorts
            if cursor:
                payload["start_cursor"] = cursor
            response = self.session.post(
                f"{self.base_url}/databases/{self.database_id}/query",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            results.extend(data.get("results", []))
            if not data.get("has_more") or len(results) >= page_size:
                return results
            cursor = data.get("next_cursor")

    def _patch(self, page_id: str, properties: dict[str, Any]) -> None:
        response = self.session.patch(
            f"{self.base_url}/pages/{page_id}",
            json={"properties": properties},
            timeout=self.timeout,
        )
        response.raise_for_status()

    def _to_item(self, page: dict[str, Any]) -> QueueItem:
        props = page.get("properties", {})
        posts = [self._plain(props.get("첫게시물", {}))]
        posts.extend(self._plain(props.get(f"답글{index}", {})) for index in range(1, 5))
        posts = [post for post in posts if post]
        scheduled = self._date(props.get("예약시각", {}))
        published = self._date(props.get("게시시각", {}))
        return QueueItem(
            page_id=page["id"],
            status=QueueStatus(self._select_name(props.get("상태", {}))),
            source_url=str(props.get("원문URL", {}).get("url") or ""),
            source_key=self._plain(props.get("TistoryID", {})),
            source_hash=self._plain(props.get("원문해시", {})),
            title=self._plain(props.get("이름", {})),
            draft=ThreadsDraft(
                format=PostFormat(self._select_name(props.get("형식", {}))),
                posts=posts,
                topic_tag=self._plain(props.get("주제태그", {})) or None,
            ),
            scheduled_at=scheduled,
            published_at=published,
            threads_ids=threads_ids_from_text(self._plain(props.get("ThreadsIDs", {}))),
            retry_count=int(props.get("재시도횟수", {}).get("number") or 0),
            error=self._plain(props.get("오류", {})),
            product_platform=self._select_name(props.get("판매플랫폼", {})),
            product_name=self._plain(props.get("상품명", {})),
            product_url=str(props.get("상품URL", {}).get("url") or ""),
            recommendation_basis=self._plain(props.get("추천근거", {})),
            disclosure=self._plain(props.get("광고고지", {})),
            product_hash=self._plain(props.get("상품해시", {})),
            content_type=self._select_name(props.get("콘텐츠유형", {})) or "블로그정보",
            publish_slot=self._plain(props.get("게시슬롯", {})),
            topic=self._plain(props.get("주제", {})),
            hook_type=self._select_name(props.get("Hook유형", {})) or None,
            blog_link_used=bool(props.get("블로그링크사용", {}).get("checkbox", False)),
            operator_note=self._plain(props.get("운영메모", {})),
            auto_generated=bool(props.get("자동생성여부", {}).get("checkbox", False)),
            human_edit_required=bool(props.get("사람수정필요", {}).get("checkbox", False)),
            dedupe_key=self._plain(props.get("중복검사키", {})),
            performance_judgement=self._select_name(props.get("성과판정", {})) or "미측정",
        )

    @staticmethod
    def _rich(value: str) -> dict[str, Any]:
        return {"rich_text": [] if not value else [{"type": "text", "text": {"content": value}}]}

    @staticmethod
    def _title(value: str) -> dict[str, Any]:
        return {"title": [{"type": "text", "text": {"content": value[:2000]}}]}

    @staticmethod
    def _select(value: str) -> dict[str, Any]:
        return {"select": {"name": value}}

    @staticmethod
    def _plain(prop: dict[str, Any]) -> str:
        values = prop.get("title") or prop.get("rich_text") or []
        return "".join(
            str(item.get("plain_text") or item.get("text", {}).get("content") or "")
            for item in values
        )

    @staticmethod
    def _select_name(prop: dict[str, Any]) -> str:
        return str((prop.get("select") or {}).get("name") or "")

    @staticmethod
    def _date(prop: dict[str, Any]) -> datetime | None:
        value = (prop.get("date") or {}).get("start")
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
