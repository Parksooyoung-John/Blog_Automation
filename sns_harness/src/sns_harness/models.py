from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
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


class ThreadsDraft(BaseModel):
    format: PostFormat
    posts: list[str]
    topic_tag: str | None = None
    rationale: str = Field(default="", max_length=500)

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


class ReviewResult(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    reviewed_draft: ThreadsDraft


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


def validate_draft_against_source(
    draft: ThreadsDraft,
    source: SourcePost,
    product: ProductOffer | None = None,
) -> list[str]:
    issues: list[str] = []
    combined = "\n".join(draft.posts)
    links = [link.rstrip(".,)") for link in URL_RE.findall(combined)]

    if product is not None:
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
    elif draft.format is PostFormat.SINGLE:
        if source.url not in draft.posts[0]:
            issues.append("single post must include the canonical source URL")
    else:
        if len(draft.posts) == 2:
            issues.append("non-product thread requires 3-5 posts")
        link_post = 1 if source.source is SourceKind.NAVER else len(draft.posts) - 1
        if any(source.url in text for index, text in enumerate(draft.posts) if index != link_post):
            issues.append("thread source URL must appear exactly once in the designated reply")
        if source.url not in draft.posts[link_post]:
            issues.append("thread must include the canonical source URL in the designated reply")

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
            + ("\n" + product.name + "\n" + product.recommendation_basis if product else "")
        )
    }
    without_urls = URL_RE.sub("", combined)
    draft_numbers = {value.rstrip(".,") for value in NUMBER_RE.findall(without_urls)}
    novel_numbers = sorted(draft_numbers - source_numbers)
    if novel_numbers:
        issues.append("draft contains numbers absent from source: " + ", ".join(novel_numbers))

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
