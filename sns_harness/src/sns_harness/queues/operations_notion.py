from __future__ import annotations

import json
from datetime import date
from typing import Any

import requests

from sns_harness.operations.models import DataRequest, OperationsEvaluation, StrategyVerdict

OPERATIONS_PROPERTY_DEFINITIONS = {
    "레코드유형": {"select": {"options": [{"name": "브리핑"}, {"name": "데이터요청"}]}},
    "날짜": {"date": {}},
    "운영상태": {"select": {"options": [{"name": n} for n in ("정상", "주의", "긴급")]}},
    "전략판정": {
        "select": {"options": [{"name": verdict.value} for verdict in StrategyVerdict]}
    },
    "판정신뢰도": {
        "select": {"options": [{"name": n} for n in ("높음", "보통", "낮음")]}
    },
    "데이터완전성": {"number": {"format": "percent"}},
    "분석기간": {"number": {"format": "number"}},
    "분석게시물수": {"number": {"format": "number"}},
    "핵심근거": {"rich_text": {}},
    "반대증거": {"rich_text": {}},
    "권장액션": {"rich_text": {}},
    "다음평가일": {"date": {}},
    "운영자결정": {"rich_text": {}},
    "운영자확인": {"checkbox": {}},
    "요청키": {"rich_text": {}},
    "요청우선순위": {
        "select": {"options": [{"name": n} for n in ("필수", "중요", "선택")]}
    },
    "요청상태": {
        "select": {"options": [{"name": n} for n in ("요청", "입력완료", "보류", "불가")]}
    },
    "요청상세": {"rich_text": {}},
}


class OperationsNotionQueue:
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

    def ensure_schema(self) -> list[str]:
        response = self.session.get(
            f"{self.base_url}/databases/{self.database_id}", timeout=self.timeout
        )
        response.raise_for_status()
        actual = response.json().get("properties", {})
        missing = {
            name: definition
            for name, definition in OPERATIONS_PROPERTY_DEFINITIONS.items()
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

    def previous_verdicts(self, limit: int = 2) -> list[StrategyVerdict]:
        pages = self._query(
            {"property": "레코드유형", "select": {"equals": "브리핑"}},
            sorts=[{"property": "날짜", "direction": "descending"}],
            page_size=limit,
        )
        names = [self._select_name(p.get("properties", {}).get("전략판정", {})) for p in pages]
        return [StrategyVerdict(name) for name in names if name]

    def request_context(self) -> tuple[set[str], set[str]]:
        pages = self._query(
            {"property": "레코드유형", "select": {"equals": "데이터요청"}}
        )
        unresolved: set[str] = set()
        suppressed: set[str] = set()
        for page in pages:
            props = page.get("properties", {})
            key = self._plain(props.get("요청키", {}))
            status = self._select_name(props.get("요청상태", {}))
            if status in ("불가", "입력완료"):
                suppressed.add(key)
            elif status in ("요청", "보류"):
                unresolved.add(key)
        return unresolved, suppressed

    def upsert_brief(self, day: date, evaluation: OperationsEvaluation) -> str:
        existing = self._query(
            {
                "and": [
                    {"property": "레코드유형", "select": {"equals": "브리핑"}},
                    {"property": "날짜", "date": {"equals": day.isoformat()}},
                ]
            },
            page_size=1,
        )
        properties = self._brief_properties(day, evaluation)
        if existing:
            page_id = existing[0]["id"]
            self._patch(page_id, properties)
        else:
            page_id = self._create(properties)
        for request in evaluation.data_requests:
            self.upsert_request(request, day)
        return page_id

    def upsert_request(self, request: DataRequest, day: date) -> str:
        existing = self._query(
            {"property": "요청키", "rich_text": {"equals": request.key}}, page_size=1
        )
        properties = {
            "이름": self._title(request.title),
            "레코드유형": self._select("데이터요청"),
            "날짜": {"date": {"start": day.isoformat()}},
            "요청키": self._rich(request.key),
            "요청우선순위": self._select(request.priority.value),
            "요청상태": self._select("요청"),
            "요청상세": self._rich(json.dumps(request.model_dump(), ensure_ascii=False)),
        }
        if not existing:
            return self._create(properties)
        page_id = existing[0]["id"]
        current = self._select_name(existing[0].get("properties", {}).get("요청상태", {}))
        if current not in ("불가", "입력완료"):
            properties.pop("요청상태")
            self._patch(page_id, properties)
        return page_id

    def _brief_properties(
        self, day: date, evaluation: OperationsEvaluation
    ) -> dict[str, Any]:
        actions = "\n".join(
            f"[{action.priority.value}] {action.title}: {action.reason}"
            for action in evaluation.actions
        )
        return {
            "이름": self._title(f"MoneyBrief 운영 브리핑 · {day.isoformat()}"),
            "레코드유형": self._select("브리핑"),
            "날짜": {"date": {"start": day.isoformat()}},
            "운영상태": self._select(evaluation.health),
            "전략판정": self._select(evaluation.verdict.value),
            "판정신뢰도": self._select(evaluation.confidence.value),
            "데이터완전성": {"number": evaluation.completeness_score / 100},
            "분석기간": {"number": evaluation.period_days},
            "분석게시물수": {"number": evaluation.measured_posts},
            "핵심근거": self._rich("\n".join(evaluation.evidence)),
            "반대증거": self._rich("\n".join(evaluation.counter_evidence)),
            "권장액션": self._rich(actions),
            "다음평가일": {"date": {"start": evaluation.next_review_at.date().isoformat()}},
        }

    def _create(self, properties: dict[str, Any]) -> str:
        response = self.session.post(
            f"{self.base_url}/pages",
            json={"parent": {"database_id": self.database_id}, "properties": properties},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return str(response.json()["id"])

    def _query(
        self,
        filter_value: dict[str, Any],
        *,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"filter": filter_value, "page_size": page_size}
        if sorts:
            payload["sorts"] = sorts
        response = self.session.post(
            f"{self.base_url}/databases/{self.database_id}/query",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return list(response.json().get("results", []))

    def _patch(self, page_id: str, properties: dict[str, Any]) -> None:
        response = self.session.patch(
            f"{self.base_url}/pages/{page_id}",
            json={"properties": properties},
            timeout=self.timeout,
        )
        response.raise_for_status()

    @staticmethod
    def _rich(value: str) -> dict[str, Any]:
        return {
            "rich_text": []
            if not value
            else [{"type": "text", "text": {"content": value[:2000]}}]
        }

    @staticmethod
    def _title(value: str) -> dict[str, Any]:
        return {"title": [{"type": "text", "text": {"content": value[:2000]}}]}

    @staticmethod
    def _select(value: str) -> dict[str, Any]:
        return {"select": {"name": value}}

    @staticmethod
    def _plain(prop: dict[str, Any]) -> str:
        values = prop.get("rich_text") or []
        return "".join(
            str(item.get("plain_text") or item.get("text", {}).get("content") or "")
            for item in values
        )

    @staticmethod
    def _select_name(prop: dict[str, Any]) -> str:
        return str((prop.get("select") or {}).get("name") or "")
