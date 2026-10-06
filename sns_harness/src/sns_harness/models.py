from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

import regex
from pydantic import BaseModel, Field, field_validator, model_validator


class PostFormat(StrEnum):
    SINGLE = "single"
    THREAD = "thread"


class QueueStatus(StrEnum):
    DRAFT = "초안"
    SALES_DRAFT_REQUESTED = "판매초안요청"
    APPROVED = "승인"
    PUBLISHING = "게시중"
    PUBLISHED = "게시완료"
    HOLD = "보류"
    ERROR = "오류"


class SourceKind(StrEnum):
    TISTORY = "tistory"
    NAVER = "naver"


class Readiness(StrEnum):
    READY = "ready"
    NEEDS_REVIEW = "needs-review"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"
    OFF_TOPIC = "off-topic"
    AFFILIATE_CHANNEL_ONLY = "affiliate-channel-only"


class ContentType(StrEnum):
    BLOG_INFO = "블로그정보"
    MONEY_TIP = "재테크팁"
    QUESTION = "질문형"
    OPERATOR = "운영글"


class SearchIntent(StrEnum):
    INFORMATION = "정보확인"
    COMPARISON = "조건비교"
    APPLICATION = "신청방법"
    CALCULATION = "계산"
    CAUTION = "주의사항"


class TrendDirection(StrEnum):
    RISING = "상승"
    STEADY = "유지"
    FALLING = "하락"


class Timeliness(StrEnum):
    EVERGREEN = "상시"
    SEASONAL = "계절"
    DEADLINE = "마감임박"


class ContentGoal(StrEnum):
    REACH = "도달"
    COMMENTS = "댓글"
    SAVES_SHARES = "저장·공유"
    BLOG_TRAFFIC = "블로그 유입"


class SampleStatus(StrEnum):
    SUFFICIENT = "충분"
    INSUFFICIENT = "부족"
    UNMEASURED = "미측정"


class HookType(StrEnum):
    CURIOSITY = "궁금증"
    NUMBER = "숫자"
    MISTAKE = "실수"
    COMPARISON = "비교"
    QUESTION = "질문"
    EMPATHY = "경험/공감"


class OfficialSource(BaseModel):
    claim: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    checked_at: datetime | None = None


class ProductPlatform(StrEnum):
    TOSS_SHARE = "토스쉐어"
    COUPANG_PARTNERS = "쿠팡파트너스"


PRODUCT_HOSTS = {
    ProductPlatform.TOSS_SHARE: "sharelink.toss.im",
    ProductPlatform.COUPANG_PARTNERS: "link.coupang.com",
}

DEFAULT_DISCLOSURES = {
    ProductPlatform.TOSS_SHARE: (
        "[광고] 이 글은 토스쇼핑 쉐어링크 활동의 일환이며, "
        "이 링크를 통한 구매가 발생하면 수수료를 지급받습니다."
    ),
    ProductPlatform.COUPANG_PARTNERS: (
        "[광고] 이 포스팅은 쿠팡 파트너스 활동의 일환으로, "
        "이에 따른 일정액의 수수료를 제공받습니다."
    ),
}


class ProductOffer(BaseModel):
    platform: ProductPlatform
    name: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    recommendation_basis: str = Field(min_length=1, max_length=2000)
    disclosure: str = Field(default="", max_length=1000)

    @field_validator("name", "url", "recommendation_basis", "disclosure")
    @classmethod
    def strip_product_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_product_contract(self) -> ProductOffer:
        parsed = urlparse(self.url)
        expected_host = PRODUCT_HOSTS[self.platform]
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != expected_host:
            raise ValueError(f"{self.platform.value} URL must use https://{expected_host}")
        if self.disclosure:
            if not self.disclosure.startswith("[광고]") or "수수료" not in self.disclosure:
                raise ValueError("custom disclosure must start with [광고] and disclose commission")
            ambiguous = ("받을 수도", "받을 수 있", "제공받을 수 있", "지급될 수 있")
            if any(phrase in self.disclosure for phrase in ambiguous):
                raise ValueError("custom disclosure must state commission without ambiguity")
        return self

    @property
    def effective_disclosure(self) -> str:
        return self.disclosure or DEFAULT_DISCLOSURES[self.platform]

    @property
    def product_hash(self) -> str:
        value = "\n".join(
            (self.platform.value, self.name, self.url, self.recommendation_basis, self.disclosure)
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SourcePost(BaseModel):
    source: SourceKind = SourceKind.TISTORY
    source_id: str
    url: str
    title: str
    content: str
    published_at: datetime
    modified_at: datetime | None = None
    description: str = ""
    image_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    information_date: datetime | None = None
    topic_category: str | None = None
    topic_grade: str | None = None
    hook_type: str | None = None
    official_sources: list[OfficialSource] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_tistory_id(cls, value: Any) -> Any:
        if isinstance(value, dict) and "source_id" not in value and "tistory_id" in value:
            value = dict(value)
            value["source_id"] = value["tistory_id"]
        return value

    @property
    def source_key(self) -> str:
        if self.source is SourceKind.NAVER:
            return f"naver:{self.source_id}"
        return self.source_id

    @property
    def tistory_id(self) -> str:
        """Compatibility accessor for the original Tistory-only interface."""
        return self.source_id

    @property
    def source_hash(self) -> str:
        normalized = "\n".join(
            part.strip() for part in (self.title, self.content) if part.strip()
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def grapheme_len(value: str) -> int:
    return len(regex.findall(r"\X", value))


def manual_source_key(content_type: str, text: str, created_at: datetime) -> str:
    digest = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:12]
    return f"manual:{created_at.date().isoformat()}:{content_type}:{digest}"


def draft_content_hash(draft: ThreadsDraft) -> str:
    value = "\n\n".join(post.strip() for post in draft.posts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ThreadsDraft(BaseModel):
    format: PostFormat
    posts: list[str]
    topic_tag: str | None = None
    rationale: str = Field(default="", max_length=500)
    hook_type: HookType | None = None
    hook_text: str = Field(default="", max_length=80)
    blog_link_used: bool = True

    @field_validator("posts")
    @classmethod
    def validate_post_texts(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("empty Threads post is not allowed")
        too_long = [index + 1 for index, text in enumerate(cleaned) if grapheme_len(text) > 480]
        if too_long:
            raise ValueError(f"Threads posts exceed 480 graphemes: {too_long}")
        return cleaned

    @field_validator("topic_tag")
    @classmethod
    def validate_topic_tag(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().lstrip("#")
        if not 1 <= grapheme_len(value) <= 50 or "." in value or "&" in value:
            raise ValueError("topic_tag must be 1-50 characters and exclude '.' and '&'")
        return value

    @model_validator(mode="after")
    def validate_format_count(self) -> ThreadsDraft:
        if self.format is PostFormat.SINGLE and len(self.posts) != 1:
            raise ValueError("single format requires exactly one post")
        if self.format is PostFormat.THREAD and not 2 <= len(self.posts) <= 5:
            raise ValueError("thread format requires 2-5 posts")
        return self


class BlogDraftCandidates(BaseModel):
    candidates: list[ThreadsDraft] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_distinct_hooks(self) -> BlogDraftCandidates:
        types = [candidate.hook_type for candidate in self.candidates]
        texts = [candidate.hook_text for candidate in self.candidates]
        if None in types or len(set(types)) != 3:
            raise ValueError("blog candidates require three distinct hook types")
        if len(set(texts)) != 3:
            raise ValueError("blog candidates require three distinct hook texts")
        return self


class ProductDraftContent(BaseModel):
    information_posts: list[str] = Field(min_length=1, max_length=4)
    sales_copy: str = Field(min_length=1, max_length=300)
    topic_tag: str | None = None
    rationale: str = Field(default="", max_length=500)

    @field_validator("information_posts")
    @classmethod
    def validate_information_posts(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("empty information post is not allowed")
        return cleaned

    @field_validator("sales_copy")
    @classmethod
    def validate_sales_copy(cls, value: str) -> str:
        return value.strip()


class DailyDraft(BaseModel):
    text: str = Field(min_length=1, max_length=480)
    topic: str = Field(default="", max_length=100)
    hook_type: HookType = HookType.CURIOSITY


class TopicResearch(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    related_keywords: list[str] = Field(default_factory=list, max_length=20)
    search_intent: SearchIntent
    trend_score: float = Field(default=0, ge=0, le=100)
    trend_direction: TrendDirection = TrendDirection.STEADY
    timeliness: Timeliness = Timeliness.EVERGREEN
    official_sources: list[OfficialSource] = Field(default_factory=list)
    channel_fit_score: float = Field(default=0, ge=0, le=100)
    evidence_score: float = Field(default=0, ge=0, le=100)
    conversation_score: float = Field(default=0, ge=0, le=100)
    duplicate_score: float = Field(default=0, ge=0, le=100)
    experiment_hypothesis: str = Field(default="", max_length=500)

    @property
    def priority_score(self) -> float:
        return round(
            self.channel_fit_score * 0.35
            + self.trend_score * 0.25
            + self.evidence_score * 0.20
            + (100 - self.duplicate_score) * 0.10
            + self.conversation_score * 0.10,
            2,
        )


class PostMetrics(BaseModel):
    window: str
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    replies: int | None = Field(default=None, ge=0)
    reposts: int | None = Field(default=None, ge=0)
    quotes_shares: int | None = Field(default=None, ge=0)
    follows: int | None = Field(default=None, ge=0)
    blog_views: int | None = Field(default=None, ge=0)
    estimated_blog_traffic: int | None = Field(default=None, ge=0)
    source: str = ""
    sample_status: SampleStatus = SampleStatus.UNMEASURED
    measured_at: datetime | None = None


class ReviewResult(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    reviewed_draft: ThreadsDraft
    quality_score: int = Field(default=0, ge=0, le=100)


class QueueItem(BaseModel):
    page_id: str
    status: QueueStatus
    source_url: str
    source_key: str
    source_hash: str
    title: str
    draft: ThreadsDraft
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    threads_ids: list[str] = Field(default_factory=list)
    retry_count: int = 0
    error: str = ""
    product_platform: str = ""
    product_name: str = ""
    product_url: str = ""
    recommendation_basis: str = ""
    disclosure: str = ""
    product_hash: str = ""
    information_date: datetime | None = None
    topic_category: str = ""
    topic_grade: str = ""
    hook_type: str = ""
    official_sources: list[OfficialSource] = Field(default_factory=list)
    readiness: Readiness = Readiness.READY
    readiness_reason: str = ""
    content_type: ContentType = ContentType.BLOG_INFO
    publish_slot: str = ""
    topic: str = ""
    hook_type: HookType | None = None
    blog_link_used: bool = False
    operator_note: str = ""
    auto_generated: bool = True
    human_edit_required: bool = False
    dedupe_key: str = ""
    performance_judgement: str = ""
    planning_keyword: str = ""
    related_keywords: list[str] = Field(default_factory=list)
    search_intent: SearchIntent | None = None
    trend_score: float | None = Field(default=None, ge=0, le=100)
    trend_direction: TrendDirection | None = None
    timeliness: Timeliness | None = None
    content_goal: ContentGoal | None = None
    experiment_hypothesis: str = ""
    metrics: dict[str, PostMetrics] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_tistory_id(cls, value: Any) -> Any:
        if isinstance(value, dict) and "source_key" not in value and "tistory_id" in value:
            value = dict(value)
            value["source_key"] = value["tistory_id"]
        return value

    @property
    def tistory_id(self) -> str:
        """Compatibility accessor for callers that still use the legacy name."""
        return self.source_key

    @property
    def has_product_input(self) -> bool:
        return any(
            (
                self.product_platform,
                self.product_name,
                self.product_url,
                self.recommendation_basis,
                self.disclosure,
            )
        )

    def to_product_offer(self) -> ProductOffer | None:
        if not self.has_product_input:
            return None
        return ProductOffer(
            platform=self.product_platform,
            name=self.product_name,
            url=self.product_url,
            recommendation_basis=self.recommendation_basis,
            disclosure=self.disclosure,
        )


URL_RE = re.compile(r"https?://\S+")
NUMBER_RE = re.compile(r"(?<![\w])\d[\d,.]*(?:%|원|억|만|회|년|월|일|시|분)?")
BLOCKED_PHRASES = (
    "무조건 유리",
    "반드시 수익",
    "확실히 돈",
    "지금 바로 가입",
    "수익을 보장",
)
SALES_BLOCKED_PHRASES = (
    "할인",
    "특가",
    "최저가",
    "품절",
    "마감 임박",
    "재고",
    "베스트",
    "1위",
    "최고",
    "유일",
    "직접 써",
    "사용해 보",
    "효능",
)
HOOK_BLOCKED_PHRASES = ("모르면 손해", "무조건", "반드시", "지금 당장")
BLOG_CTA_PHRASES = ("프로필 블로그", "블로그에 정리", "자세한 내용은 블로그")
GENERIC_TITLE_WORDS = {
    "기준", "계산", "방법", "순서", "이유", "조건", "신청", "조회", "정리"
}


def _topic_words(title: str) -> set[str]:
    words: set[str] = set()
    for raw in re.findall(r"[가-힣A-Za-z]{3,}", title):
        word = re.sub(r"(?:으로|에서|까지|부터|에게|보다|처럼|은|는|이|가|을|를)$", "", raw)
        if len(word) >= 3 and word not in GENERIC_TITLE_WORDS:
            words.add(word.lower())
    return words


def _validate_naver_hook(draft: ThreadsDraft, source: SourcePost) -> list[str]:
    issues: list[str] = []
    hook = draft.hook_text.strip()
    if not hook or draft.hook_type is None:
        return ["Naver blog draft requires hook_text and hook_type"]
    if not draft.posts[0].startswith(hook):
        issues.append("hook_text must be the exact prefix of the first post")
    if not 15 <= grapheme_len(hook) <= 80:
        issues.append("hook_text must be 15-80 characters")
    if len([part for part in re.split(r"[.!?？]+", hook) if part.strip()]) > 2:
        issues.append("hook_text must contain at most two sentences")
    normalized_hook = re.sub(r"\W+", "", hook).lower()
    normalized_title = re.sub(r"\W+", "", source.title).lower()
    if normalized_title and SequenceMatcher(None, normalized_hook, normalized_title).ratio() >= 0.8:
        issues.append("hook_text must not repeat the source title")
    if not any(word in hook.lower() for word in _topic_words(source.title)):
        issues.append("hook_text must name a concrete topic from the source title")
    if any(phrase in hook for phrase in HOOK_BLOCKED_PHRASES):
        issues.append("hook_text contains a blocked urgency or fear expression")
    if draft.hook_type is HookType.QUESTION and not any(mark in hook for mark in ("?", "？")):
        issues.append("question hook must contain a question mark")
    if draft.hook_type is HookType.NUMBER and not NUMBER_RE.search(hook):
        issues.append("number hook must contain a source-backed number")
    if draft.hook_type is HookType.COMPARISON and not any(
        marker in hook.lower() for marker in ("vs", "차이", "보다", "둘")
    ):
        issues.append("comparison hook must express a comparison")
    if draft.hook_type is HookType.MISTAKE and not any(
        marker in hook for marker in ("놓치", "실수", "헷갈", "착각", "잘못", "그냥")
    ):
        issues.append("mistake hook must identify a likely mistake or confusion")
    if draft.hook_type is HookType.EMPATHY:
        issues.append("blog drafts cannot fabricate experience or empathy hooks")
    return issues


def validate_draft_against_source(
    draft: ThreadsDraft,
    source: SourcePost | None,
    product: ProductOffer | None = None,
) -> list[str]:
    issues: list[str] = []
    combined = "\n".join(draft.posts)
    links = [link.rstrip(".,)") for link in URL_RE.findall(combined)]

    if source is not None and source.source is SourceKind.NAVER and product is None:
        issues.extend(_validate_naver_hook(draft, source))

    if source is None:
        if product is not None:
            issues.append("product draft requires a source post")
        if links:
            issues.append("manual content must not contain links")
    elif product is not None:
        if draft.format is not PostFormat.THREAD or not 2 <= len(draft.posts) <= 5:
            issues.append("product draft must be a 2-5 post thread")
        else:
            if not draft.posts[0].startswith("[광고 포함]"):
                issues.append("product thread first post must start with [광고 포함]")
            source_link_count = sum(source.url in post for post in draft.posts)
            if source.url not in draft.posts[-2] or source_link_count != 1:
                issues.append("product thread source URL must appear once in the penultimate post")
            if product.url not in draft.posts[-1] or links.count(product.url) != 1:
                issues.append("product URL must appear once in the final sales reply")
            if not draft.posts[-1].startswith(product.effective_disclosure):
                issues.append("final sales reply must start with the required disclosure")
            if not draft.posts[-1].rstrip().endswith(product.url):
                issues.append("final sales reply must end with the product URL")
            sales_copy = draft.posts[-1]
            for phrase in SALES_BLOCKED_PHRASES:
                if phrase in sales_copy:
                    issues.append(f"blocked sales expression: {phrase}")
            if re.search(r"\d[\d,.]*\s*(?:원|%)", URL_RE.sub("", sales_copy)):
                issues.append("sales reply must not contain price or discount claims")
    elif not draft.blog_link_used:
        if source.url in combined or links:
            issues.append("link-free blog draft must not contain URLs")
        if any(phrase in combined for phrase in BLOG_CTA_PHRASES):
            issues.append("link-free blog draft must not contain a blog CTA")
    elif draft.format is PostFormat.SINGLE:
        if source.url not in draft.posts[0] or links.count(source.url) != 1:
            issues.append("single post must include the canonical source URL once")
    else:
        if len(draft.posts) == 2:
            issues.append("non-product thread requires 3-5 posts")
        link_post = 1 if source.source is SourceKind.NAVER else len(draft.posts) - 1
        if any(source.url in text for index, text in enumerate(draft.posts) if index != link_post):
            issues.append("thread source URL must appear exactly once in the designated reply")
        if source.url not in draft.posts[link_post]:
            issues.append("thread must include the canonical source URL in the designated reply")

    if source is not None:
        allowed_links = {source.url}
        if product is not None:
            allowed_links.add(product.url)
        foreign_links = [link for link in links if link not in allowed_links]
        if foreign_links:
            issues.append("draft contains a link outside the approved URLs")

        source_numbers = {
            value.rstrip(".,")
            for value in NUMBER_RE.findall(
                source.title
                + "\n"
                + source.content
                + (
                    "\n" + product.name + "\n" + product.recommendation_basis
                    if product
                    else ""
                )
            )
        }
        without_urls = URL_RE.sub("", combined)
        draft_numbers = {value.rstrip(".,") for value in NUMBER_RE.findall(without_urls)}
        novel_numbers = sorted(draft_numbers - source_numbers)
        if novel_numbers:
            issues.append(
                "draft contains numbers absent from source: " + ", ".join(novel_numbers)
            )

    for phrase in BLOCKED_PHRASES:
        if phrase in combined:
            issues.append(f"blocked financial expression: {phrase}")
    return issues


def classify_readiness(
    source: SourcePost,
    *,
    product: ProductOffer | None = None,
) -> tuple[Readiness, str]:
    """Apply deterministic channel and evidence gates before human approval."""
    text = f"{source.title}\n{source.content}".lower()
    finance_terms = (
        "실업급여", "지원금", "세액", "전세", "상속", "퇴직", "연금",
        "isa", "irp", "etf", "보험", "리볼빙", "수수료",
    )
    product_terms = ("화장지", "세제", "식품", "패션", "생활용품")
    if product is not None and not any(term in text for term in finance_terms):
        return Readiness.AFFILIATE_CHANNEL_ONLY, "금융정보와 직접 관련되지 않은 상품입니다."
    if not any(term in text for term in finance_terms):
        return Readiness.OFF_TOPIC, "머니브리프 금융정보 주제와 직접 관련되지 않습니다."
    if product is None and any(term in text for term in product_terms):
        return Readiness.AFFILIATE_CHANNEL_ONLY, "일반 상품은 상품판매 채널에서만 게시합니다."
    if not source.official_sources or source.information_date is None:
        return Readiness.INSUFFICIENT_EVIDENCE, "공식 출처와 정보 기준일이 필요합니다."
    return Readiness.READY, "필수 근거와 금융 주제 조건을 충족했습니다."


def validate_content_contract(item: QueueItem) -> list[str]:
    """Validate non-blog daily content before it can be approved."""
    text = "\n".join(item.draft.posts)
    issues: list[str] = []
    if item.content_type is ContentType.MONEY_TIP and not 100 <= grapheme_len(text) <= 220:
        issues.append("재테크팁은 100~220자여야 합니다.")
    if item.content_type is ContentType.QUESTION:
        if not 80 <= grapheme_len(text) <= 180:
            issues.append("질문형은 80~180자여야 합니다.")
        if text.count("?") + text.count("？") != 1:
            issues.append("질문형은 질문을 정확히 1개 포함해야 합니다.")
        if URL_RE.search(text):
            issues.append("질문형에는 링크를 넣을 수 없습니다.")
    if item.content_type is ContentType.OPERATOR:
        if not item.operator_note.strip():
            issues.append("운영글은 운영메모가 필요합니다.")
        if not item.human_edit_required:
            issues.append("운영글은 사람 수정이 필요합니다.")
        if URL_RE.search(text):
            issues.append("운영글에는 기본적으로 링크를 넣을 수 없습니다.")
    return issues


def threads_ids_to_text(ids: list[str]) -> str:
    return json.dumps(ids, ensure_ascii=False, separators=(",", ":"))


def threads_ids_from_text(value: str) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic schema to the strict object contract required by Responses."""
    schema = deepcopy(model.model_json_schema())

    def visit(node: object) -> None:
        if isinstance(node, dict):
            # Responses strict schemas reject Pydantic's JSON Schema ``default``
            # keyword, including defaults on enum fields such as DailyDraft.hook_type.
            node.pop("default", None)
            properties = node.get("properties")
            if node.get("type") == "object" and isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema
