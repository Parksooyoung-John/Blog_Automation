from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from sns_harness.models import (
    URL_RE,
    ProductDraftContent,
    ProductOffer,
    SourcePost,
    ThreadsDraft,
    strict_json_schema,
)


class ThreadsWriter:
    def __init__(self, api_key: str, model: str, prompt_path: Path) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.instructions = prompt_path.read_text(encoding="utf-8")
        self.sales_instructions = prompt_path.with_name("sales_writer.md").read_text(
            encoding="utf-8"
        )

    def generate(self, source: SourcePost) -> ThreadsDraft:
        payload = {
            "title": source.title,
            "canonical_url": source.url,
            "published_at": source.published_at.isoformat(),
            "description": source.description,
            "tags": source.tags,
            "content": source.content[:30_000],
        }
        last_error: ValidationError | None = None
        for attempt in range(3):
            request_payload = {
                **payload,
                "generation_attempt": attempt + 1,
                "previous_validation_error": str(last_error) if last_error else "",
            }
            response = self.client.responses.create(
                model=self.model,
                instructions=self.instructions,
                input=json.dumps(request_payload, ensure_ascii=False),
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
            try:
                return ThreadsDraft.model_validate_json(response.output_text)
            except ValidationError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def generate_for_product(
        self,
        source: SourcePost,
        product: ProductOffer,
        existing_draft: ThreadsDraft,
    ) -> ThreadsDraft:
        payload = {
            "source": {
                "title": source.title,
                "canonical_url": source.url,
                "published_at": source.published_at.isoformat(),
                "description": source.description,
                "tags": source.tags,
                "content": source.content[:30_000],
            },
            "product": {
                "platform": product.platform.value,
                "name": product.name,
                "recommendation_basis": product.recommendation_basis,
            },
            "existing_draft": existing_draft.model_dump(mode="json"),
        }
        last_error: Exception | None = None
        for attempt in range(3):
            request_payload = {
                **payload,
                "generation_attempt": attempt + 1,
                "previous_validation_error": str(last_error) if last_error else "",
            }
            response = self.client.responses.create(
                model=self.model,
                instructions=self.sales_instructions,
                input=json.dumps(request_payload, ensure_ascii=False),
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "product_threads_draft",
                        "strict": True,
                        "schema": strict_json_schema(ProductDraftContent),
                    }
                },
            )
            try:
                content = ProductDraftContent.model_validate_json(response.output_text)
                return self._compose_product_draft(source, product, content)
            except (ValidationError, ValueError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    @staticmethod
    def _compose_product_draft(
        source: SourcePost,
        product: ProductOffer,
        content: ProductDraftContent,
    ) -> ThreadsDraft:
        information_posts = [URL_RE.sub("", post).strip() for post in content.information_posts]
        information_posts[0] = "[광고 포함]\n" + information_posts[0]
        information_posts[-1] = information_posts[-1].rstrip() + f"\n{source.url}"
        sales_copy = URL_RE.sub("", content.sales_copy).strip()
        sales_post = f"{product.effective_disclosure}\n{sales_copy}\n{product.url}"
        return ThreadsDraft(
            format="thread",
            posts=[*information_posts, sales_post],
            topic_tag=content.topic_tag,
            rationale=content.rationale,
        )
