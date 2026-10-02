from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from sns_harness.agents.writer import ThreadsWriter
from sns_harness.models import BlogDraftCandidates, HookType, SourcePost, ThreadsDraft


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
    valid = ThreadsDraft(
        format="single",
        posts=[f"총보수와 추적오차를 확인합니다. {source.url}"],
        topic_tag="ETF",
        hook_type=HookType.CURIOSITY,
        hook_text="ETF 비용에서 놓치기 쉬운 부분이 있음.",
    )
    valid_candidates = BlogDraftCandidates(
        candidates=[
            valid,
            valid.model_copy(
                update={
                    "hook_type": HookType.MISTAKE,
                    "hook_text": "ETF 비용에서 흔히 놓치는 부분이 있음.",
                }
            ),
            valid.model_copy(
                update={
                    "hook_type": HookType.QUESTION,
                    "hook_text": "ETF 비용 차이를 정확히 확인하고 있어?",
                }
            ),
        ]
    )
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
