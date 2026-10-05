from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import requests

from sns_harness.models import TrendDirection


@dataclass(frozen=True)
class TrendSnapshot:
    group_name: str
    keywords: tuple[str, ...]
    score: float
    direction: TrendDirection
    series: tuple[dict[str, Any], ...]


class NaverDataLabClient:
    endpoint = "https://openapi.naver.com/v1/datalab/search"

    def __init__(self, client_id: str, client_secret: str, *, timeout: float = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        )

    def search(
        self,
        keyword_groups: list[tuple[str, list[str]]],
        *,
        start_date: date,
        end_date: date,
    ) -> list[TrendSnapshot]:
        snapshots: list[TrendSnapshot] = []
        for offset in range(0, len(keyword_groups), 5):
            payload = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "timeUnit": "date",
                "keywordGroups": [
                    {"groupName": name, "keywords": keywords}
                    for name, keywords in keyword_groups[offset : offset + 5]
                ],
            }
            response = self.session.post(self.endpoint, json=payload, timeout=self.timeout)
            response.raise_for_status()
            snapshots.extend(self._parse(response.json()))
        return snapshots

    @staticmethod
    def _parse(data: dict[str, Any]) -> list[TrendSnapshot]:
        raw = data.get("results") or []
        averages = [
            sum(float(point.get("ratio", 0)) for point in item.get("data", []))
            / max(len(item.get("data", [])), 1)
            for item in raw
        ]
        maximum = max(averages, default=0.0)
        result: list[TrendSnapshot] = []
        for item, average in zip(raw, averages, strict=True):
            series = tuple(item.get("data", []))
            midpoint = max(len(series) // 2, 1)
            before = sum(float(p.get("ratio", 0)) for p in series[:midpoint]) / midpoint
            after_points = series[midpoint:] or series[-1:]
            after = sum(float(p.get("ratio", 0)) for p in after_points) / len(after_points)
            if after > before * 1.1:
                direction = TrendDirection.RISING
            elif after < before * 0.9:
                direction = TrendDirection.FALLING
            else:
                direction = TrendDirection.STEADY
            result.append(
                TrendSnapshot(
                    group_name=str(item.get("title", "")),
                    keywords=tuple(item.get("keywords") or ()),
                    score=round((average / maximum) * 100, 2) if maximum else 0.0,
                    direction=direction,
                    series=series,
                )
            )
        return result


def default_date_range(days: int) -> tuple[date, date]:
    end = date.today()
    return end - timedelta(days=max(days, 1) - 1), end
