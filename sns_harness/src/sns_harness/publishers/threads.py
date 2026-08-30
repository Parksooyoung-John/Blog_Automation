from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from sns_harness.models import QueueItem


class ThreadsAPIError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ThreadsPublisher:
    def __init__(
        self,
        user_id: str,
        access_token: str,
        *,
        timeout: float = 20,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_id = user_id
        self.access_token = access_token
        self.timeout = timeout
        self.session = session or requests.Session()
        self.sleep = sleep
        self.base_url = "https://graph.threads.net/v1.0"

    def publishing_quota(self) -> tuple[int, int]:
        response = self._request(
            "GET",
            f"/{self.user_id}/threads_publishing_limit",
            params={
                "fields": "quota_usage,config",
                "access_token": self.access_token,
            },
        )
        rows = response.get("data", [])
        if not rows:
            return 0, 250
        row = rows[0]
        return int(row.get("quota_usage", 0)), int(row.get("config", {}).get("quota_total", 250))

    def publish(
        self,
        item: QueueItem,
        save_progress: Callable[[list[str]], None],
    ) -> list[str]:
        quota_usage, quota_total = self.publishing_quota()
        missing_count = len(item.draft.posts) - len(item.threads_ids)
        if quota_usage + missing_count > quota_total:
            raise ThreadsAPIError(
                f"Threads publishing quota insufficient: {quota_usage}/{quota_total}"
            )

        ids = list(item.threads_ids)
        for index, text in enumerate(item.draft.posts):
            if index < len(ids):
                continue

            reconciled = self.find_recent_exact(text)
            if reconciled:
                ids.append(reconciled)
                save_progress(ids)
                continue

            parent_id = ids[-1] if ids else None
            media_id = self._create_and_publish(
                text=text,
                parent_id=parent_id,
                topic_tag=item.draft.topic_tag if index == 0 else None,
            )
            ids.append(media_id)
            save_progress(ids)
        return ids

    def find_recent_exact(self, text: str) -> str | None:
        response = self._request(
            "GET",
            f"/{self.user_id}/threads",
            params={
                "fields": "id,text,timestamp",
                "limit": 50,
                "access_token": self.access_token,
            },
        )
        cutoff = datetime.now(UTC) - timedelta(hours=48)
        for row in response.get("data", []):
            timestamp = row.get("timestamp")
            if timestamp:
                created = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if created < cutoff:
                    continue
            if str(row.get("text") or "").strip() == text.strip():
                return str(row["id"])
        return None

    def _create_and_publish(
        self,
        *,
        text: str,
        parent_id: str | None,
        topic_tag: str | None,
    ) -> str:
        payload: dict[str, Any] = {
            "media_type": "TEXT",
            "text": text,
            "access_token": self.access_token,
        }
        if parent_id:
            payload["reply_to_id"] = parent_id
        if topic_tag:
            payload["topic_tag"] = topic_tag
        container = self._request("POST", f"/{self.user_id}/threads", data=payload)
        creation_id = str(container.get("id") or "")
        if not creation_id:
            raise ThreadsAPIError("Threads container response did not include an id")

        self._wait_until_ready(creation_id)

        published = self._request(
            "POST",
            f"/{self.user_id}/threads_publish",
            data={"creation_id": creation_id, "access_token": self.access_token},
        )
        media_id = str(published.get("id") or "")
        if not media_id:
            raise ThreadsAPIError("Threads publish response did not include an id")
        return media_id

    def _wait_until_ready(self, creation_id: str) -> None:
        for attempt in range(10):
            container = self._request(
                "GET",
                f"/{creation_id}",
                params={
                    "fields": "status,error_message",
                    "access_token": self.access_token,
                },
            )
            status = str(container.get("status") or "").upper()
            if status == "FINISHED":
                return
            if status in {"ERROR", "EXPIRED"}:
                detail = str(container.get("error_message") or "unknown container error")
                raise ThreadsAPIError(f"Threads container {status}: {detail}")
            if attempt < 9:
                self.sleep(3)
        raise ThreadsAPIError(
            "Threads container was not ready after 30 seconds",
            retryable=True,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        last_error = ""
        for attempt in range(3):
            try:
                response = self.session.request(
                    method,
                    f"{self.base_url}{path}",
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt == 2:
                    break
                self.sleep(2**attempt)
                continue

            if response.status_code < 400:
                return response.json()
            try:
                payload = response.json()
                last_error = str(payload.get("error", {}).get("message") or payload)
            except ValueError:
                last_error = response.text[:500]

            if response.status_code not in {429, 500, 502, 503, 504}:
                raise ThreadsAPIError(f"Threads API {response.status_code}: {last_error}")
            if attempt < 2:
                retry_after = response.headers.get("Retry-After")
                self.sleep(float(retry_after) if retry_after else 2**attempt)
        raise ThreadsAPIError(
            f"Threads API request failed after retries: {last_error}",
            retryable=True,
        )
