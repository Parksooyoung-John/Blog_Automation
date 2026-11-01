from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from sns_harness.agents.writer import ThreadsWriter, candidate_plan
from sns_harness.models import (
    BlogDraftCandidates,
    DailyDraft,
    HookType,
    SourcePost,
    ThreadsDraft,
)


def test_writer_retries_invalid_thread_count() -> None:
    source = SourcePost(
        tistory_id="46",
        url="https://j2gblog.tistory.com/46",
        title="ETF 용어",
        content="총보수와 추적오차를 확인합니다.",
        published_at=datetime.now(UTC),
    )
    invalid = {"candidates": [{
        "format": "thread", "posts": ["하나", "둘", "셋", "넷", "다섯", "여섯"],
        "topic_tag": "ETF", "rationale": "", "hook_type": "궁금증",
        "hook_text": "ETF 비용에서 놓치기 쉬운 부분이 있음.", "blog_link_used": True,
    }]}
    plan = candidate_plan(True)
    texts = [
        "ETF 총보수 숫자부터 확인해요",
        "ETF 비용에서 흔히 놓치는 부분",
        "ETF 총보수 vs 추적오차 차이",
        "ETF 고르다 막막했던 적 있죠",
        "ETF 비용 정확히 확인하고 있어?",
    ]
    all_candidates = [
        ThreadsDraft(
            format="single",
            posts=[
                "총보수와 추적오차를 확인합니다."
                + (f" {source.url}" if entry["include_blog_link"] else "")
            ],
            topic_tag="ETF",
            hook_type=HookType(entry["hook_type"]),
            hook_text=text,
            candidate_type=entry["candidate_type"],
            blog_link_used=entry["include_blog_link"],
        )
        for entry, text in zip(plan, texts, strict=True)
    ]
    valid = all_candidates[0]
    valid_candidates = BlogDraftCandidates(candidates=all_candidates)
    create = Mock(
        side_effect=[
            SimpleNamespace(output_text=json.dumps(invalid, ensure_ascii=False)),
            SimpleNamespace(output_text=valid_candidates.model_dump_json()),
        ]
    )
    writer = ThreadsWriter.__new__(ThreadsWriter)
    writer.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    writer.model = "test-model"
    writer.instructions = "write"

    result = writer.generate(source)

    assert result == valid
    assert create.call_count == 2
    second_input = json.loads(create.call_args_list[1].kwargs["input"])
    assert "thread format requires 2-5 posts" in second_input["previous_validation_error"]


def test_writer_retries_daily_draft_without_a_real_hook() -> None:
    source = SourcePost(
        tistory_id="46",
        url="https://blog.naver.com/education_blog/46",
        title="근로장려금 기한후 신청",
        content="기한후 신청은 11월 30일까지 가능하고 지급액은 10% 감액됩니다.",
        published_at=datetime.now(UTC),
    )
    invalid = DailyDraft(
        text="기한후 신청은 11월 30일까지 가능합니다.",
        topic="근로장려금",
        hook_type=HookType.CURIOSITY,
        hook_text="기한후 신청은 11월 30일까지 가능합니다.",
    )
    valid = DailyDraft(
        text=(
            "근로장려금, 신청을 놓쳤다고 끝난 건 아님.\n"
            "기한후 신청은 11월 30일까지 가능하지만 지급액은 10% 감액됩니다."
        ),
        topic="근로장려금",
        hook_type=HookType.CURIOSITY,
        hook_text="근로장려금, 신청을 놓쳤다고 끝난 건 아님.",
    )
    create = Mock(
        side_effect=[
            SimpleNamespace(output_text=invalid.model_dump_json()),
            SimpleNamespace(output_text=valid.model_dump_json()),
        ]
    )
    writer = ThreadsWriter.__new__(ThreadsWriter)
    writer.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    writer.model = "test-model"
    writer.daily_instructions = "write"

    result = writer.generate_daily(source, "재테크팁")

    assert result == valid
    assert create.call_count == 2
    second_input = json.loads(create.call_args_list[1].kwargs["input"])
    assert "줄바꿈" in second_input["previous_validation_error"]
