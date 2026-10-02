from datetime import datetime

import pytest
from pydantic import ValidationError

from sns_harness.models import (
    PostFormat,
    ProductOffer,
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


def test_thread_requires_two_to_five_posts() -> None:
    with pytest.raises(ValidationError):
        ThreadsDraft(format=PostFormat.THREAD, posts=["하나"])

    with pytest.raises(ValidationError):
        ThreadsDraft(format=PostFormat.THREAD, posts=[str(index) for index in range(6)])


def test_two_post_thread_requires_product_context() -> None:
    draft = ThreadsDraft(
        format=PostFormat.THREAD,
        posts=["요약", f"원문 {source().url}"],
    )

    assert "non-product thread requires 3-5 posts" in validate_draft_against_source(
        draft, source()
    )


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


def test_number_comparison_ignores_trailing_sentence_punctuation() -> None:
    post = source().model_copy(
        update={"content": "금융감독원 1332 경찰청 112 체크리스트 4 항목"}
    )
    draft = ThreadsDraft(
        format="single",
        posts=[f"금융감독원 1332, 경찰청 112, 체크리스트 4. {post.url}"],
    )

    assert validate_draft_against_source(draft, post) == []


def test_manual_content_can_be_validated_without_a_source_post() -> None:
    draft = ThreadsDraft(
        format="single",
        posts=["ISA 만기 자금은 어떤 기준으로 운용 방향을 정하고 계신가요?"],
    )

    assert validate_draft_against_source(draft, None) == []


def test_manual_content_rejects_external_links() -> None:
    draft = ThreadsDraft(
        format="single",
        posts=["의견이 궁금합니다. https://example.com"],
    )

    assert "manual content must not contain links" in validate_draft_against_source(
        draft, None
    )


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


def test_product_thread_link_and_disclosure_contract() -> None:
    product = ProductOffer(
        platform="토스쉐어",
        name="취득세 안내서",
        url="https://sharelink.toss.im/example",
        recommendation_basis="취득세 조건을 다시 확인할 때 참고할 수 있는 안내서",
    )
    draft = ThreadsDraft(
        format="thread",
        posts=[
            "[광고 포함]\n취득세 감면은 조건 확인이 중요합니다.\n"
            "https://j2gblog.tistory.com/165",
            f"{product.effective_disclosure}\n조건을 정리할 때 참고해 보세요.\n{product.url}",
        ],
    )

    assert validate_draft_against_source(draft, source(), product) == []


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        ("토스쉐어", "http://sharelink.toss.im/example"),
        ("토스쉐어", "https://example.com/product"),
        ("쿠팡파트너스", "https://sharelink.toss.im/example"),
    ],
)
def test_product_offer_rejects_unapproved_urls(platform: str, url: str) -> None:
    with pytest.raises(ValidationError):
        ProductOffer(
            platform=platform,
            name="상품",
            url=url,
            recommendation_basis="추천 근거",
        )


def test_product_offer_rejects_ambiguous_custom_disclosure() -> None:
    with pytest.raises(ValidationError):
        ProductOffer(
            platform="쿠팡파트너스",
            name="상품",
            url="https://link.coupang.com/a/example",
            recommendation_basis="추천 근거",
            disclosure="[광고] 구매하면 수수료를 받을 수 있습니다.",
        )
