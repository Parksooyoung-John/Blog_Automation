from sns_harness.models import (
    ContentType,
    HookType,
    QueueItem,
    QueueStatus,
    ThreadsDraft,
    validate_content_contract,
)


def item(content_type: ContentType, text: str, **kwargs) -> QueueItem:
    return QueueItem(
        page_id="page",
        status=QueueStatus.DRAFT,
        source_url="",
        source_key="manual:test",
        source_hash="hash",
        title="test",
        draft=ThreadsDraft(format="single", posts=[text]),
        content_type=content_type,
        **kwargs,
    )


def test_question_requires_one_question_and_no_link() -> None:
    text = "연금저축이랑 IRP 둘 다 하고 있어? 하나만 고르면 어떤 기준으로 골랐어?"
    issues = validate_content_contract(item(ContentType.QUESTION, text))
    assert "질문형은 질문을 정확히 1개 포함해야 합니다." in issues


def test_operator_requires_note_and_human_edit() -> None:
    issues = validate_content_contract(item(ContentType.OPERATOR, "오늘 운영 기록"))
    assert "운영글은 운영메모가 필요합니다." in issues
    assert "운영글은 사람 수정이 필요합니다." in issues


def test_operator_with_note_and_edit_is_valid() -> None:
    issues = validate_content_contract(
        item(
            ContentType.OPERATOR,
            "조회수보다 팔로우가 중요한 이유를 다시 확인했다.",
            operator_note="오늘 인사이트 메모",
            human_edit_required=True,
            hook_type=HookType.EMPATHY,
        )
    )
    assert issues == []
