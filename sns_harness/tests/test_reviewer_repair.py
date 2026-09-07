from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from sns_harness.agents.reviewer import ComplianceReviewer
from sns_harness.models import SourcePost, ThreadsDraft


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
