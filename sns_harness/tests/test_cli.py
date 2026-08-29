from __future__ import annotations

from unittest.mock import Mock

import requests

from sns_harness.__main__ import validate
from sns_harness.config import Settings


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
