from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from sns_harness.models import SourcePost, ThreadsDraft, strict_json_schema


class ThreadsWriter:
    def __init__(self, api_key: str, model: str, prompt_path: Path) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.instructions = prompt_path.read_text(encoding="utf-8")

    def generate(self, source: SourcePost) -> ThreadsDraft:
        payload = {
            "title": source.title,
            "canonical_url": source.url,
            "published_at": source.published_at.isoformat(),
            "description": source.description,
            "tags": source.tags,
            "content": source.content[:30_000],
        }
        response = self.client.responses.create(
            model=self.model,
            instructions=self.instructions,
            input=json.dumps(payload, ensure_ascii=False),
            store=False,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "threads_draft",
                    "strict": True,
                    "schema": strict_json_schema(ThreadsDraft),
                }
            },
        )
        return ThreadsDraft.model_validate_json(response.output_text)
