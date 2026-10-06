from datetime import UTC, datetime

from sns_harness.models import (
    ContentType,
    DailyDraft,
    HookType,
    QueueItem,
    QueueStatus,
    ThreadsDraft,
    manual_source_key,
    validate_content_contract,
    validate_daily_draft,
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


def test_manual_source_key_is_stable_and_namespaced() -> None:
    created_at = datetime(2026, 10, 2, tzinfo=UTC)
    first = manual_source_key("질문형", "ISA 질문", created_at)
    second = manual_source_key("질문형", "ISA 질문", created_at)
    assert first == second
    assert first.startswith("manual:2026-10-02:질문형:")


def test_daily_tip_requires_a_real_hook_on_a_separate_first_line() -> None:
    draft = DailyDraft(
        text=(
            "근로장려금, 신청을 놓쳤다고 끝난 건 아님.\n"
            "기한후 신청은 11월 30일까지 가능하지만 지급액은 10% 감액됩니다."
        ),
        topic="근로장려금",
        hook_type=HookType.CURIOSITY,
        hook_text="근로장려금, 신청을 놓쳤다고 끝난 건 아님.",
    )

    assert validate_daily_draft(draft, ContentType.MONEY_TIP) == []


def test_daily_tip_rejects_a_default_label_without_a_hook() -> None:
    draft = DailyDraft(
        text="기한후 신청은 11월 30일까지 가능합니다.",
        topic="근로장려금",
        hook_type=HookType.CURIOSITY,
        hook_text="기한후 신청은 11월 30일까지 가능합니다.",
    )

    assert "Hook문구 뒤에는 줄바꿈 후 핵심 정보를 작성해야 합니다." in validate_daily_draft(
        draft, ContentType.MONEY_TIP
    )
