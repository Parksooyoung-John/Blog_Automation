from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from sns_harness.models import QueueItem


class StrategyVerdict(StrEnum):
    INSUFFICIENT = "판단유보"
    KEEP = "유지"
    IMPROVE = "개선"
    REVIEW_PIVOT = "전환검토"
    PIVOT = "전환권고"
    RECOVER = "운영복구"


class Confidence(StrEnum):
    LOW = "낮음"
    MEDIUM = "보통"
    HIGH = "높음"


class RequestPriority(StrEnum):
    REQUIRED = "필수"
    IMPORTANT = "중요"
    OPTIONAL = "선택"


class DataRequest(BaseModel):
    key: str
    title: str
    priority: RequestPriority
    missing_data: str
    reason: str
    impact: str
    input_location: str
    minimum_required: str
    completion_check: str
    fallback_scope: str


class RecommendedAction(BaseModel):
    priority: RequestPriority
    title: str
    reason: str
    target: str = ""


class SegmentPerformance(BaseModel):
    content_type: str
    hook_type: str
    publish_slot: str
    blog_link_used: bool
    sample_size: int
    median_views: float
    median_actions: float
    repeatable: bool


class OperationsSnapshot(BaseModel):
    generated_at: datetime
    period_days: int = Field(default=30, ge=1)
    items: list[QueueItem] = Field(default_factory=list)
    github_status_available: bool = False
    github_failures: int = Field(default=0, ge=0)
    search_trend_available: bool = False
    unresolved_request_keys: set[str] = Field(default_factory=set)
    suppressed_request_keys: set[str] = Field(default_factory=set)
    previous_verdicts: list[StrategyVerdict] = Field(default_factory=list)


class OperationsEvaluation(BaseModel):
    verdict: StrategyVerdict
    confidence: Confidence
    health: str
    completeness_score: int = Field(ge=0, le=100)
    period_days: int
    total_published: int
    measured_posts: int
    evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    actions: list[RecommendedAction] = Field(default_factory=list)
    data_requests: list[DataRequest] = Field(default_factory=list, max_length=5)
    segments: list[SegmentPerformance] = Field(default_factory=list)
    next_review_at: datetime
    summary: str
