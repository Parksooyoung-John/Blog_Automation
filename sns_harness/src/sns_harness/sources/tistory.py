from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from sns_harness.models import SourcePost

NUMERIC_PATH_RE = re.compile(r"^/(\d+)/?$")


class TistorySource:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 20,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent", "j2g-sns-harness/0.1 (+https://j2gblog.tistory.com)"
        )

    def discover(self, limit: int = 20) -> list[str]:
        urls = self._discover_from_rss(limit)
        if len(urls) < limit:
            urls.extend(self._discover_from_home(limit - len(urls), existing=set(urls)))
        return urls[:limit]

    def _discover_from_rss(self, limit: int) -> list[str]:
        try:
            response = self.session.get(f"{self.base_url}/rss", timeout=self.timeout)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError):
            return []

        urls: list[str] = []
        for item in root.findall(".//item"):
            link = (item.findtext("link") or "").strip()
            canonical = self._numeric_url(link)
            if canonical and canonical not in urls:
                urls.append(canonical)
                if len(urls) >= limit:
                    break
        return urls

    def _discover_from_home(self, needed: int, existing: set[str]) -> list[str]:
        found: list[str] = []
        page = 1
        while len(found) < needed and page <= 5:
            url = self.base_url if page == 1 else f"{self.base_url}/?page={page}"
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException:
                break
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.select("a[href]"):
                canonical = self._numeric_url(urljoin(self.base_url, anchor.get("href", "")))
                if canonical and canonical not in existing and canonical not in found:
                    found.append(canonical)
                    if len(found) >= needed:
                        break
            page += 1
        return found

    def _numeric_url(self, value: str) -> str | None:
        parsed = urlparse(value)
        if parsed.netloc and parsed.netloc != urlparse(self.base_url).netloc:
            return None
        match = NUMERIC_PATH_RE.match(parsed.path)
        return f"{self.base_url}/{match.group(1)}" if match else None

    def fetch(self, url: str) -> SourcePost:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return self.parse(response.text, url)

    def parse(self, html: str, fallback_url: str) -> SourcePost:
        soup = BeautifulSoup(html, "html.parser")
        data = self._blog_posting_json_ld(soup)
        canonical = (
            soup.select_one('link[rel="canonical"]') or soup.select_one('meta[property="og:url"]')
        )
        canonical_url = (
            canonical.get("href") or canonical.get("content") if canonical else fallback_url
        )
        numeric_url = self._numeric_url(str(canonical_url)) or self._numeric_url(fallback_url)
        if not numeric_url:
            raise ValueError(f"not a numeric Tistory post URL: {canonical_url}")

        title = str(
            data.get("headline")
            or self._meta(soup, "og:title")
            or (soup.select_one("h1").get_text(" ", strip=True) if soup.select_one("h1") else "")
        ).strip()
        published = data.get("datePublished") or self._meta(soup, "article:published_time")
        if not published:
            raise ValueError(f"published date not found: {numeric_url}")

        body = None
        for selector in (
            ".contents_style",
            ".tt_article_useless_p_margin",
            ".entry-content",
            "article",
        ):
            body = soup.select_one(selector)
            if body:
                break
        if not body:
            raise ValueError(f"article body not found: {numeric_url}")
        for removable in body.select(
            "script, style, noscript, form, .container_postbtn, "
            ".another_category, .related-articles"
        ):
            removable.decompose()
        content = re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True)).strip()

        tags = []
        for anchor in soup.select('.tag_label a, a[rel="tag"]'):
            tag = anchor.get_text(" ", strip=True).lstrip("#")
            if tag and tag not in tags:
                tags.append(tag)

        modified = data.get("dateModified")
        return SourcePost(
            tistory_id=numeric_url.rsplit("/", 1)[-1],
            url=numeric_url,
            title=unescape(title),
            content=content,
            published_at=datetime.fromisoformat(str(published).replace("Z", "+00:00")),
            modified_at=(
                datetime.fromisoformat(str(modified).replace("Z", "+00:00")) if modified else None
            ),
            description=unescape(
                str(data.get("description") or self._meta(soup, "og:description") or "")
            ),
            image_url=(
                str(data.get("image", {}).get("url"))
                if isinstance(data.get("image"), dict)
                else self._meta(soup, "og:image")
            ),
            tags=tags,
        )

    @staticmethod
    def _meta(soup: BeautifulSoup, property_name: str) -> str | None:
        node = soup.select_one(f'meta[property="{property_name}"]')
        return str(node.get("content")) if node and node.get("content") else None

    @staticmethod
    def _blog_posting_json_ld(soup: BeautifulSoup) -> dict[str, object]:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                value = json.loads(script.get_text(strip=True))
            except json.JSONDecodeError:
                continue
            candidates = value if isinstance(value, list) else [value]
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate.get("@type") == "BlogPosting":
                    return candidate
        return {}
