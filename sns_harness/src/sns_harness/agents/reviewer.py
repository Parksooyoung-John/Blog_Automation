from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from sns_harness.models import (
    ReviewResult,
    SourcePost,
    ThreadsDraft,
    strict_json_schema,
    validate_draft_against_source,
)


class ComplianceReviewer:
    def __init__(self, api_key: str, model: str, prompt_path: Path) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.instructions = prompt_path.read_text(encoding="utf-8")

    def review(self, source: SourcePost, draft: ThreadsDraft) -> ReviewResult:
        current_draft = draft
        remaining_issues = validate_draft_against_source(current_draft, source)

        for attempt in range(3):
            payload = {
                "source": {
                    "title": source.title,
                    "canonical_url": source.url,
                    "published_at": source.published_at.isoformat(),
                    "content": source.content[:30_000],
                },
                "draft": current_draft.model_dump(mode="json"),
                "deterministic_issues": remaining_issues,
                "repair_attempt": attempt + 1,
            }
            response = self.client.responses.create(
                model=self.model,
                instructions=self.instructions,
                input=json.dumps(payload, ensure_ascii=False),
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "threads_review",
                        "strict": True,
                        "schema": strict_json_schema(ReviewResult),
                    }
                },
            )
            try:
                result = ReviewResult.model_validate_json(response.output_text)
            except ValidationError as exc:
                remaining_issues = [f"검수 출력 형식 오류: {exc.errors()[0]['msg']}"]
                continue

            current_draft = result.reviewed_draft
            remaining_issues = list(
                dict.fromkeys(
                    result.issues + validate_draft_against_source(current_draft, source)
                )
            )
            if not remaining_issues and result.approved:
                return result
            if not remaining_issues:
                remaining_issues = ["수정안이 검수 승인을 받지 못했습니다."]

        return ReviewResult(
            approved=False,
            issues=remaining_issues,
            reviewed_draft=current_draft,
        )
