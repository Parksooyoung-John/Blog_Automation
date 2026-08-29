from datetime import datetime

import pytest
from pydantic import ValidationError

from sns_harness.models import (
    PostFormat,
    SourcePost,
    ThreadsDraft,
    strict_json_schema,
    validate_draft_against_source,
)


def source() -> SourcePost:
    return SourcePost(
        tistory_id="165",
        url="https://j2gblog.tistory.com/165",
        title="취득세 감면",
        content="12억 원 이하 주택은 최대 200만 원 감면 조건을 확인해야 합니다.",
        published_at=datetime.fromisoformat("2026-08-22T11:38:07+09:00"),
    )


def test_single_requires_exactly_one_post() -> None:
    with pytest.raises(ValidationError):
        ThreadsDraft(format=PostFormat.SINGLE, posts=["하나", "둘"])


def test_thread_requires_three_to_five_posts() -> None:
    with pytest.raises(ValidationError):
        ThreadsDraft(format=PostFormat.THREAD, posts=["하나", "둘"])


def test_thread_link_only_in_last_reply() -> None:
    draft = ThreadsDraft(
        format="thread",
        posts=[
            "감면에는 가격 조건이 있습니다.",
            "12억 원 이하인지 먼저 확인해야 합니다.",
            "기준일은 원문에서 확인하세요. https://j2gblog.tistory.com/165",
        ],
        topic_tag="취득세",
    )
    assert validate_draft_against_source(draft, source()) == []


def test_novel_number_is_rejected() -> None:
    draft = ThreadsDraft(
        format="single",
        posts=["최대 300만 원입니다. https://j2gblog.tistory.com/165"],
    )
    issues = validate_draft_against_source(draft, source())
    assert any("300만" in issue for issue in issues)


def test_post_has_480_grapheme_safety_limit() -> None:
    with pytest.raises(ValidationError):
        ThreadsDraft(
            format="single",
            posts=["가" * 481],
        )


def test_openai_schema_is_strict_at_every_object() -> None:
    schema = strict_json_schema(ThreadsDraft)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    for definition in schema.get("$defs", {}).values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
            assert set(definition["required"]) == set(definition["properties"])
