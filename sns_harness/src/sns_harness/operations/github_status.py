from __future__ import annotations

from datetime import UTC, datetime, timedelta

import requests


class GitHubActionsStatus:
    def __init__(self, token: str, repository: str, *, timeout: float = 20) -> None:
        self.token = token
        self.repository = repository
        self.timeout = timeout

    def recent_failures(self, *, days: int = 7, per_page: int = 50) -> tuple[bool, int]:
        if not self.token or not self.repository:
            return False, 0
        response = requests.get(
            f"https://api.github.com/repos/{self.repository}/actions/runs",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={
                "per_page": per_page,
                "created": f">={(datetime.now(UTC) - timedelta(days=days)).date().isoformat()}",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
        relevant = [
            run
            for run in runs
            if run.get("name") in ("Blog SNS sync", "Blog SNS publish")
        ]
        failures = sum(run.get("conclusion") == "failure" for run in relevant)
        return True, failures
