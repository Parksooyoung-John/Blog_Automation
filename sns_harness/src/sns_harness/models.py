from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from enum import StrEnum
from typing import Any

import regex
from pydantic import BaseModel, Field, field_validator, model_validator


class PostFormat(StrEnum):
    SINGLE = "single"
    THREAD = "thread"


class QueueStatus(StrEnum):
    DRAFT = "초안"
    APPROVED = "승인"
    PUBLISHING = "게시중"
    PUBLISHED = "게시완료"
    HOLD = "보류"
    ERROR = "오류"


class SourcePost(BaseModel):
    tistory_id: str
    url: str
    title: str
    content: str
    published_at: datetime
    modified_at: datetime | None = None
    description: str = ""
    image_url: str | None = None
    tags: list[str] = Field(default_factory=list)

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
        if self.format is PostFormat.THREAD and not 3 <= len(self.posts) <= 5:
            raise ValueError("thread format requires 3-5 posts")
        return self


class ReviewResult(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    reviewed_draft: ThreadsDraft


class QueueItem(BaseModel):
    page_id: str
    status: QueueStatus
    source_url: str
    tistory_id: str
    source_hash: str
    title: str
    draft: ThreadsDraft
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    threads_ids: list[str] = Field(default_factory=list)
    retry_count: int = 0
    error: str = ""


URL_RE = re.compile(r"https?://\S+")
NUMBER_RE = re.compile(r"(?<![\w])\d[\d,.]*(?:%|원|억|만|회|년|월|일|시|분)?")
BLOCKED_PHRASES = (
    "무조건 유리",
    "반드시 수익",
    "확실히 돈",
    "지금 바로 가입",
    "수익을 보장",
)


def validate_draft_against_source(draft: ThreadsDraft, source: SourcePost) -> list[str]:
    issues: list[str] = []
    combined = "\n".join(draft.posts)
    links = URL_RE.findall(combined)

    if draft.format is PostFormat.SINGLE:
        if source.url not in draft.posts[0]:
            issues.append("single post must include the canonical source URL")
    else:
        if any(source.url in text for text in draft.posts[:-1]):
            issues.append("thread source URL is allowed only in the final reply")
        if source.url not in draft.posts[-1]:
            issues.append("thread final reply must include the canonical source URL")

    foreign_links = [link.rstrip(".,)") for link in links if not link.startswith(source.url)]
    if foreign_links:
        issues.append("draft contains a link other than the canonical source URL")

    source_numbers = set(NUMBER_RE.findall(source.title + "\n" + source.content))
    without_urls = URL_RE.sub("", combined)
    draft_numbers = set(NUMBER_RE.findall(without_urls))
    novel_numbers = sorted(draft_numbers - source_numbers)
    if novel_numbers:
        issues.append("draft contains numbers absent from source: " + ", ".join(novel_numbers))

    for phrase in BLOCKED_PHRASES:
        if phrase in combined:
            issues.append(f"blocked financial expression: {phrase}")
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
