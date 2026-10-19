from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from sns_harness.agents.reviewer import ComplianceReviewer
from sns_harness.models import SourcePost, ThreadsDraft


def _reviewer(*responses: dict) -> tuple[ComplianceReviewer, Mock]:
    create = Mock(
        side_effect=[
            SimpleNamespace(output_text=json.dumps(r, ensure_ascii=False)) for r in responses
        ]
    )
    reviewer = ComplianceReviewer.__new__(ComplianceReviewer)
    reviewer.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    reviewer.model = "test-model"
    reviewer.instructions = "repair"
    return reviewer, create


def _source_and_draft(posts_text: str) -> tuple[SourcePost, ThreadsDraft]:
    source = SourcePost(
        tistory_id="165",
        url="https://j2gblog.tistory.com/165",
        title="취득세 감면",
        content="12억 원 이하 조건을 확인해야 합니다.",
        published_at=datetime.now(UTC),
    )
    return source, ThreadsDraft(format="single", posts=[posts_text.format(url=source.url)])


def test_approved_draft_is_not_held_by_issues_that_only_describe_fixes() -> None:
    source, draft = _source_and_draft("12억 원 이하 조건을 확인하세요. {url}")
    reviewer, create = _reviewer({
        "approved": True,
        "issues": ["훅을 더 구체적으로 수정했습니다."],
        "reviewed_draft": draft.model_dump(mode="json"),
    })

    result = reviewer.review(source, draft)

    assert result.approved is True
    assert create.call_count == 1


def test_approved_flag_cannot_override_a_deterministic_failure() -> None:
    source, draft = _source_and_draft("12억 원 이하 조건을 확인하세요.")   # canonical URL missing
    reviewer, create = _reviewer(*[{
        "approved": True,
        "issues": [],
        "reviewed_draft": draft.model_dump(mode="json"),
    }] * 3)

    result = reviewer.review(source, draft)

    assert result.approved is False
    assert any("canonical source URL" in issue for issue in result.issues)
    assert create.call_count == 3


def test_reviewer_retries_until_repaired_draft_is_approved() -> None:
    source = SourcePost(
        tistory_id="165",
        url="https://j2gblog.tistory.com/165",
        title="취득세 감면",
        content="12억 원 이하 조건을 확인해야 합니다.",
        published_at=datetime.now(UTC),
    )
    draft = ThreadsDraft(
        format="single",
        posts=[f"12억 원 이하 조건을 확인하세요. {source.url}"],
    )
    first = {
        "approved": False,
        "issues": ["표현을 더 정확히 수정해야 합니다."],
        "reviewed_draft": draft.model_dump(mode="json"),
    }
    second = {
        "approved": True,
        "issues": [],
        "reviewed_draft": draft.model_dump(mode="json"),
    }
    create = Mock(
        side_effect=[
            SimpleNamespace(output_text=json.dumps(first, ensure_ascii=False)),
            SimpleNamespace(output_text=json.dumps(second, ensure_ascii=False)),
        ]
    )
    reviewer = ComplianceReviewer.__new__(ComplianceReviewer)
    reviewer.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    reviewer.model = "test-model"
    reviewer.instructions = "repair"

    result = reviewer.review(source, draft)

    assert result.approved is True
    assert result.issues == []
    assert create.call_count == 2
