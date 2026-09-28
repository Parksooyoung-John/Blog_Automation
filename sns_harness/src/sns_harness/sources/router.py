from __future__ import annotations

from urllib.parse import urlparse

from sns_harness.models import SourcePost
from sns_harness.sources.naver import NaverSource
from sns_harness.sources.tistory import TistorySource


class PublishSourceRouter:
    """Route publish-time source validation by the stored canonical URL."""

    def __init__(self, tistory: TistorySource, naver: NaverSource) -> None:
        self.tistory = tistory
        self.naver = naver
        self.tistory_host = urlparse(tistory.base_url).hostname

    def fetch(self, url: str) -> SourcePost:
        host = urlparse(url).hostname
        if host == self.tistory_host:
            return self.tistory.fetch(url)
        if host in {"blog.naver.com", "m.blog.naver.com"}:
            return self.naver.fetch(url)
        raise ValueError(f"unsupported source URL: {url}")
