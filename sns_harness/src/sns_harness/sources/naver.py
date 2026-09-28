from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sns_harness.models import SourceKind, SourcePost

BLOG_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
POST_PATH_RE = re.compile(r"^/([^/]+)/([^/]+)/?$")
ADD_DATE_RE = re.compile(r'(?:"addDate"|\baddDate)\s*[:=]\s*["\']?(\d{10,13})')
TAG_NAME_RE = re.compile(r'var\s+gsTagName\s*=\s*"((?:\\.|[^"\\])*)"')


class NaverSource:
    def __init__(
        self,
        blog_id: str,
        *,
        timeout: float = 20,
        session: requests.Session | None = None,
    ) -> None:
        if not BLOG_ID_RE.fullmatch(blog_id):
            raise ValueError(f"invalid Naver blog ID: {blog_id!r}")
        self.blog_id = blog_id
        self.timeout = timeout
        self.session = session or requests.Session()
        if session is None:
            retry = Retry(
                total=4,
                backoff_factor=1,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=("GET",),
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
        self.session.headers.setdefault(
            "User-Agent", f"j2g-sns-harness/0.1 (+https://blog.naver.com/{blog_id})"
        )
        self.session.headers.setdefault("Referer", f"https://m.blog.naver.com/{blog_id}")

    def discover(self, limit: int = 20) -> list[str]:
        if limit <= 0:
            return []

        urls: list[str] = []
        seen: set[str] = set()
        page = 1
        page_size = 20
        while len(urls) < limit:
            response = self.session.get(
                f"https://m.blog.naver.com/api/blogs/{self.blog_id}/post-list",
                params={"categoryNo": 0, "itemCount": page_size, "page": page},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result")
            if not isinstance(result, dict):
                raise ValueError("Naver post list response has no result object")
            items = result.get("items")
            if not isinstance(items, list):
                raise ValueError("Naver post list response has no items list")
            if not items:
                break

            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Naver post list contains an invalid item")
                log_no = self._validate_log_no(str(item.get("logNo") or ""))
                if log_no not in seen:
                    seen.add(log_no)
                    urls.append(self._canonical_url(log_no))
                    if len(urls) >= limit:
                        break

            total_count = result.get("totalCount")
            if isinstance(total_count, int) and page * page_size >= total_count:
                break
            page += 1
        return urls

    def fetch(self, url: str) -> SourcePost:
        log_no = self._log_no_from_url(url)
        mobile_url = f"https://m.blog.naver.com/{self.blog_id}/{log_no}"
        response = self.session.get(mobile_url, timeout=self.timeout)
        response.raise_for_status()
        return self.parse(response.text, url)

    def parse(self, html: str, fallback_url: str) -> SourcePost:
        fallback_log_no = self._log_no_from_url(fallback_url)
        soup = BeautifulSoup(html, "html.parser")

        canonical_value = self._meta(soup, "og:url") or fallback_url
        try:
            log_no = self._log_no_from_url(canonical_value)
        except ValueError:
            log_no = fallback_log_no
        canonical_url = self._canonical_url(log_no)

        title = unescape(self._meta(soup, "og:title") or "").strip()
        if not title:
            raise ValueError(f"Naver post title not found: {canonical_url}")

        body = soup.select_one(".se-main-container")
        if body is None:
            raise ValueError(f"Naver article body not found: {canonical_url}")
        for removable in body.select("script, style, noscript, form"):
            removable.decompose()
        content = body.get_text("\n", strip=True).replace("\u200b", "")
        content = re.sub(r"[ \t\r\f\v]+", " ", content)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()
        if not content:
            raise ValueError(f"Naver article body is empty: {canonical_url}")

        published_match = ADD_DATE_RE.search(html)
        if not published_match:
            raise ValueError(f"Naver published date not found: {canonical_url}")
        timestamp = int(published_match.group(1))
        if timestamp >= 10_000_000_000:
            timestamp /= 1000

        tags: list[str] = []
        tag_match = TAG_NAME_RE.search(html)
        if tag_match:
            try:
                tag_text = json.loads(f'"{tag_match.group(1)}"')
            except json.JSONDecodeError:
                tag_text = tag_match.group(1)
            for value in tag_text.split(","):
                tag = unescape(value).strip().lstrip("#")
                if tag and tag not in tags:
                    tags.append(tag)

        return SourcePost(
            source=SourceKind.NAVER,
            source_id=log_no,
            url=canonical_url,
            title=title,
            content=content,
            published_at=datetime.fromtimestamp(timestamp, UTC),
            description=unescape(self._meta(soup, "og:description") or ""),
            image_url=self._meta(soup, "og:image"),
            tags=tags,
        )

    def _log_no_from_url(self, value: str) -> str:
        parsed = urlparse(value)
        if parsed.hostname not in {"blog.naver.com", "m.blog.naver.com"}:
            raise ValueError(f"not a Naver blog post URL: {value}")
        match = POST_PATH_RE.fullmatch(parsed.path)
        if not match or match.group(1) != self.blog_id:
            raise ValueError(f"not a post URL for Naver blog {self.blog_id}: {value}")
        return self._validate_log_no(match.group(2))

    @staticmethod
    def _validate_log_no(value: str) -> str:
        if not value.isdigit():
            raise ValueError(f"invalid Naver logNo: {value!r}")
        return value

    def _canonical_url(self, log_no: str) -> str:
        return f"https://blog.naver.com/{self.blog_id}/{log_no}"

    @staticmethod
    def _meta(soup: BeautifulSoup, property_name: str) -> str | None:
        node = soup.select_one(
            f'meta[property="{property_name}"], meta[name="{property_name}"]'
        )
        return str(node.get("content")) if node and node.get("content") else None
