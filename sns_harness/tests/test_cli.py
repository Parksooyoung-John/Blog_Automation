from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
import requests

from sns_harness.__main__ import main, parser, validate
from sns_harness.config import Settings
from sns_harness.models import SourceKind, SourcePost


def configured_settings() -> Settings:
    return Settings(
        OPENAI_API_KEY="openai-test",
        NOTION_API_KEY="notion-test",
        NOTION_SNS_DATABASE_ID="database-test",
        THREADS_USER_ID="threads-user",
        THREADS_ACCESS_TOKEN="threads-token",
    )


def test_validate_reports_unshared_notion_database(monkeypatch, capsys) -> None:
    response = Mock(status_code=404)
    error = requests.HTTPError(response=response)
    queue = Mock()
    queue.validate_schema.side_effect = error
    monkeypatch.setattr("sns_harness.__main__.notion_queue", lambda settings: queue)

    assert validate(configured_settings(), "all") == 2
    assert "Share the SNS database" in capsys.readouterr().err


def test_validate_reports_notion_connection_failure(monkeypatch, capsys) -> None:
    queue = Mock()
    queue.validate_schema.side_effect = requests.ConnectionError("offline")
    monkeypatch.setattr("sns_harness.__main__.notion_queue", lambda settings: queue)

    assert validate(configured_settings(), "all") == 2
    assert "Could not connect to Notion API" in capsys.readouterr().err


def test_sync_source_defaults_to_naver_and_keeps_tistory_compatibility() -> None:
    assert parser().parse_args(["sync"]).source == "naver"
    assert parser().parse_args(["sync", "--source", "tistory"]).source == "tistory"
    assert parser().parse_args(["prepare-sales", "--dry-run"]).dry_run is True
    assert parser().parse_args(["sync", "--retry-errors"]).retry_errors is True


def test_naver_dry_run_does_not_create_drafts_or_openai_clients(
    monkeypatch, capsys
) -> None:
    post = SourcePost(
        source=SourceKind.NAVER,
        source_id="123",
        url="https://blog.naver.com/education_blog/123",
        title="네이버 글",
        content="본문",
        published_at=datetime.now(UTC),
    )

    class Source:
        def __init__(self, blog_id: str, *, timeout: float) -> None:
            assert blog_id == "education_blog"

        def discover(self, limit: int) -> list[str]:
            return [post.url]

        def fetch(self, url: str) -> SourcePost:
            return post

    class Queue:
        writes = 0

        def find_by_source_key(self, source_key: str):
            assert source_key == "naver:123"
            return None

        def create(self, source, review) -> None:
            self.writes += 1

    queue = Queue()
    monkeypatch.setattr("sns_harness.__main__.get_settings", configured_settings)
    monkeypatch.setattr("sns_harness.__main__.notion_queue", lambda settings: queue)
    monkeypatch.setattr("sns_harness.__main__.NaverSource", Source)
    monkeypatch.setattr(
        "sns_harness.__main__.ThreadsWriter",
        lambda *args, **kwargs: pytest.fail("dry-run must not construct an OpenAI writer"),
    )

    assert main(["sync", "--source", "naver", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["created"] == 1
    assert queue.writes == 0


def test_prepare_sales_dry_run_does_not_construct_openai_clients(
    monkeypatch, capsys
) -> None:
    class Queue:
        def sales_draft_requests(self):
            return []

    monkeypatch.setattr("sns_harness.__main__.get_settings", configured_settings)
    monkeypatch.setattr("sns_harness.__main__.notion_queue", lambda settings: Queue())
    monkeypatch.setattr(
        "sns_harness.__main__.ThreadsWriter",
        lambda *args, **kwargs: pytest.fail("dry-run must not construct an OpenAI writer"),
    )

    assert main(["prepare-sales", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["candidates"] == 0
