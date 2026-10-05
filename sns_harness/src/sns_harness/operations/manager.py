from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median

from sns_harness.models import QueueItem, QueueStatus
from sns_harness.operations.models import (
    Confidence,
    DataRequest,
    OperationsEvaluation,
    OperationsSnapshot,
    RecommendedAction,
    RequestPriority,
    SegmentPerformance,
    StrategyVerdict,
)

PIVOT_MESSAGE = "쓰레드 망했어요. 다른 컨셉으로 새롭게 해보시죠."


class DailyOperationsManager:
    """Deterministic advisor. It never mutates publishing queue state."""

    def evaluate(self, snapshot: OperationsSnapshot) -> OperationsEvaluation:
        published = [item for item in snapshot.items if item.status is QueueStatus.PUBLISHED]
        measured = [item for item in published if self._views(item) is not None]
        requests = self._data_requests(snapshot, published, measured)
        completeness = self._completeness(snapshot, published)
        operational_issues = self._operational_issues(snapshot)
        experiments = {
            item.experiment_hypothesis or item.content_type.value for item in measured
        }
        segments = self._segments(measured)

        evidence: list[str] = []
        counter: list[str] = []
        actions = self._operational_actions(snapshot, operational_issues)

        if operational_issues:
            verdict = StrategyVerdict.RECOVER
            confidence = Confidence.HIGH
            evidence.append(f"게시·예약 운영 이상 {operational_issues}건이 확인됐습니다.")
            summary = "콘텐츠 성과 판단보다 게시 운영 복구가 먼저 필요합니다."
        elif snapshot.period_days < 28 or len(measured) < 20 or len(experiments) < 3:
            verdict = StrategyVerdict.INSUFFICIENT
            confidence = Confidence.LOW
            evidence.append(
                f"측정 가능 게시물 {len(measured)}건, 실험 {len(experiments)}개로 "
                "전환 판단 최소 기준을 충족하지 못했습니다."
            )
            summary = "현재 데이터만으로는 콘셉트 성공 또는 실패를 단정할 수 없습니다."
        else:
            current, previous = self._split_periods(measured)
            reach_improved = self._median_views(current) > self._median_views(previous)
            action_improved = self._median_actions(current) > self._median_actions(previous)
            repeatable = any(segment.repeatable for segment in segments)
            evidence.extend(
                [
                    f"최근 도달 중앙값 개선 여부: {reach_improved}",
                    f"최근 목표 행동 중앙값 개선 여부: {action_improved}",
                ]
            )
            if repeatable:
                counter.append("세부 조합 중 repeatable 판정이 있어 전체 전환 근거는 약합니다.")
            if reach_improved and action_improved:
                verdict = StrategyVerdict.KEEP
                confidence = Confidence.HIGH
                summary = "도달과 목표 행동이 함께 개선되어 현재 전략을 유지할 근거가 있습니다."
            elif reach_improved or action_improved or repeatable:
                verdict = StrategyVerdict.IMPROVE
                confidence = Confidence.MEDIUM
                summary = "일부 개선 신호가 있어 전체 전환보다 우수 조합 확대가 적절합니다."
                actions.append(
                    RecommendedAction(
                        priority=RequestPriority.IMPORTANT,
                        title="성과가 확인된 조합을 다음 주 실험에 확대",
                        reason="일부 지표 또는 세부 조합에서 개선 신호가 확인됐습니다.",
                    )
                )
            else:
                prior_review = bool(
                    snapshot.previous_verdicts
                    and snapshot.previous_verdicts[0] is StrategyVerdict.REVIEW_PIVOT
                )
                if prior_review:
                    verdict = StrategyVerdict.PIVOT
                    confidence = Confidence.HIGH
                    summary = PIVOT_MESSAGE + " 2회 연속 평가에서 개선 신호를 찾지 못했습니다."
                else:
                    verdict = StrategyVerdict.REVIEW_PIVOT
                    confidence = Confidence.MEDIUM
                    summary = "여러 실험에서 개선 신호가 없어 다음 주에도 전환 여부를 재평가합니다."
                actions.append(
                    RecommendedAction(
                        priority=RequestPriority.REQUIRED,
                        title="현재 콘셉트의 전환 실험 준비",
                        reason="도달과 목표 행동이 모두 직전 기간보다 개선되지 않았습니다.",
                    )
                )

        return OperationsEvaluation(
            verdict=verdict,
            confidence=confidence,
            health="긴급" if operational_issues else "주의" if requests else "정상",
            completeness_score=completeness,
            period_days=snapshot.period_days,
            total_published=len(published),
            measured_posts=len(measured),
            evidence=evidence[:3],
            counter_evidence=counter,
            actions=actions,
            data_requests=requests,
            segments=segments,
            next_review_at=snapshot.generated_at + timedelta(days=7),
            summary=summary,
        )

    @staticmethod
    def _views(item: QueueItem) -> int | None:
        for window in ("72h", "24h"):
            metric = item.metrics.get(window)
            if metric and metric.views is not None:
                return metric.views
        return None

    @staticmethod
    def _actions(item: QueueItem) -> int:
        metric = item.metrics.get("72h") or item.metrics.get("24h")
        if not metric:
            return 0
        return sum(
            value or 0
            for value in (metric.replies, metric.reposts, metric.quotes_shares, metric.follows)
        )

    def _split_periods(self, items: list[QueueItem]) -> tuple[list[QueueItem], list[QueueItem]]:
        ordered = sorted(
            items,
            key=lambda item: item.published_at
            or item.scheduled_at
            or datetime.min.replace(tzinfo=UTC),
        )
        midpoint = len(ordered) // 2
        return ordered[midpoint:], ordered[:midpoint]

    def _median_views(self, items: list[QueueItem]) -> float:
        values = [value for item in items if (value := self._views(item)) is not None]
        return float(median(values)) if values else 0.0

    def _median_actions(self, items: list[QueueItem]) -> float:
        return float(median([self._actions(item) for item in items])) if items else 0.0

    def _segments(self, items: list[QueueItem]) -> list[SegmentPerformance]:
        if not items:
            return []
        grouped: dict[tuple[str, str, str, bool], list[QueueItem]] = {}
        for item in items:
            key = (
                item.content_type.value,
                item.hook_type.value if item.hook_type else "미측정",
                item.publish_slot or "미측정",
                item.blog_link_used,
            )
            grouped.setdefault(key, []).append(item)
        overall_views = self._median_views(items)
        overall_actions = self._median_actions(items)
        result = []
        for key, values in grouped.items():
            views = self._median_views(values)
            actions = self._median_actions(values)
            result.append(
                SegmentPerformance(
                    content_type=key[0],
                    hook_type=key[1],
                    publish_slot=key[2],
                    blog_link_used=key[3],
                    sample_size=len(values),
                    median_views=views,
                    median_actions=actions,
                    repeatable=(
                        len(values) >= 3
                        and views > overall_views
                        and actions > overall_actions
                    ),
                )
            )
        return sorted(result, key=lambda segment: (-segment.sample_size, segment.content_type))

    @staticmethod
    def _operational_issues(snapshot: OperationsSnapshot) -> int:
        now = snapshot.generated_at
        queue_issues = sum(
            item.status is QueueStatus.ERROR
            or (
                item.status in (QueueStatus.APPROVED, QueueStatus.PUBLISHING)
                and item.scheduled_at is not None
                and item.scheduled_at < now
                and not item.threads_ids
            )
            for item in snapshot.items
        )
        return queue_issues + snapshot.github_failures

    @staticmethod
    def _operational_actions(
        snapshot: OperationsSnapshot, operational_issues: int
    ) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        if operational_issues:
            actions.append(
                RecommendedAction(
                    priority=RequestPriority.REQUIRED,
                    title="게시·예약 오류부터 복구",
                    reason=f"운영 이상 {operational_issues}건이 성과 측정을 왜곡합니다.",
                )
            )
        unscheduled = sum(
            item.status is QueueStatus.APPROVED and item.scheduled_at is None
            for item in snapshot.items
        )
        if unscheduled:
            actions.append(
                RecommendedAction(
                    priority=RequestPriority.IMPORTANT,
                    title="승인 후 미예약 항목 확인",
                    reason=f"승인됐지만 예약되지 않은 항목이 {unscheduled}건 있습니다.",
                )
            )
        return actions

    def _data_requests(
        self,
        snapshot: OperationsSnapshot,
        published: list[QueueItem],
        measured: list[QueueItem],
    ) -> list[DataRequest]:
        candidates: list[DataRequest] = []
        if published and not any(
            metric.blog_views is not None
            for item in published
            for metric in item.metrics.values()
        ):
            candidates.append(
                DataRequest(
                    key="naver-blog-views",
                    title="네이버 블로그 조회수 입력",
                    priority=RequestPriority.IMPORTANT,
                    missing_data="링크형 게시물의 네이버 블로그 조회수",
                    reason="Threads에서 블로그로 이어지는 전환 신호를 확인해야 합니다.",
                    impact="블로그 유입 목표의 성과 신뢰도가 낮아집니다.",
                    input_location="SNS 게시 큐의 블로그조회수",
                    minimum_required="최근 링크형 게시물 5건",
                    completion_check="링크형 5건의 조회수가 모두 입력됐는지 확인",
                    fallback_scope="Threads 내부 반응만 평가 가능",
                )
            )
        if not snapshot.github_status_available:
            candidates.append(
                DataRequest(
                    key="github-actions-read",
                    title="GitHub Actions 읽기 권한 확인",
                    priority=RequestPriority.IMPORTANT,
                    missing_data="최근 sync/publish workflow 실행 결과",
                    reason="미게시 원인이 콘텐츠인지 자동화 장애인지 분리해야 합니다.",
                    impact="운영 장애 진단 신뢰도가 낮아집니다.",
                    input_location="workflow permissions의 actions: read",
                    minimum_required="최근 7일 workflow 실행 이력",
                    completion_check="브리핑에 workflow 성공·실패가 표시되는지 확인",
                    fallback_scope="Notion 오류 상태만으로 운영 장애 판단",
                )
            )
        if not snapshot.search_trend_available:
            candidates.append(
                DataRequest(
                    key="naver-datalab",
                    title="네이버 데이터랩 API 연결",
                    priority=RequestPriority.OPTIONAL,
                    missing_data="키워드 상대 검색 추세",
                    reason="다음 주제 후보의 시의성을 비교하기 위해 필요합니다.",
                    impact="주제 추천은 과거 게시 성과에만 의존합니다.",
                    input_location="NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET",
                    minimum_required="최근 30일 키워드 추세",
                    completion_check="research-topics 명령이 결과를 반환하는지 확인",
                    fallback_scope="Notion 기록 기반 주제 추천만 가능",
                )
            )
        return [
            request
            for request in candidates
            if request.key not in snapshot.suppressed_request_keys
        ][:5]

    @staticmethod
    def _completeness(snapshot: OperationsSnapshot, published: list[QueueItem]) -> int:
        checks = [
            bool(published),
            bool(published) and all(item.threads_ids for item in published),
            bool(published) and all(item.published_at for item in published),
            bool(published) and all(item.content_type for item in published),
            bool(published) and all(item.hook_type for item in published),
            bool(published) and any(item.metrics for item in published),
            snapshot.github_status_available,
            snapshot.search_trend_available,
        ]
        return round(sum(checks) / len(checks) * 100)
