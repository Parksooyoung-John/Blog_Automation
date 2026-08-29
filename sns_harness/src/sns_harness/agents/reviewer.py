from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

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
        deterministic_issues = validate_draft_against_source(draft, source)
        payload = {
            "source": {
                "title": source.title,
                "canonical_url": source.url,
                "published_at": source.published_at.isoformat(),
                "content": source.content[:30_000],
            },
            "draft": draft.model_dump(mode="json"),
            "deterministic_issues": deterministic_issues,
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
        result = ReviewResult.model_validate_json(response.output_text)
        final_issues = validate_draft_against_source(result.reviewed_draft, source)
        if final_issues or result.issues:
            return ReviewResult(
                approved=False,
                issues=list(dict.fromkeys(result.issues + final_issues)),
                reviewed_draft=result.reviewed_draft,
            )
        return result
