from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sns_harness.models import SourceKind
from sns_harness.sources.naver import NaverSource

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class FakeListSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.pages = {
            page: json.loads(
                (FIXTURES / f"naver-list-page-{page}.json").read_text(encoding="utf-8")
            )
            for page in (1, 2)
        }
        self.requested_pages: list[int] = []

    def get(self, url: str, *, params: dict[str, int], timeout: float) -> FakeResponse:
        assert url.endswith("/api/blogs/education_blog/post-list")
        assert params["itemCount"] == 20
        self.requested_pages.append(params["page"])
        return FakeResponse(self.pages[params["page"]])


def test_discover_paginates_deduplicates_and_builds_canonical_urls() -> None:
    session = FakeListSession()
    source = NaverSource("education_blog", session=session)

    assert source.discover(3) == [
        "https://blog.naver.com/education_blog/101",
        "https://blog.naver.com/education_blog/102",
        "https://blog.naver.com/education_blog/103",
    ]
    assert session.requested_pages == [1, 2]


def test_parse_naver_post_body_metadata_date_and_gs_tag_name() -> None:
    html = (FIXTURES / "naver-post.html").read_text(encoding="utf-8")
    post = NaverSource("education_blog").parse(
        html, "https://m.blog.naver.com/education_blog/224423197601"
    )

    assert post.source is SourceKind.NAVER
    assert post.source_id == "224423197601"
    assert post.source_key == "naver:224423197601"
    assert post.tistory_id == "224423197601"
    assert post.url == "https://blog.naver.com/education_blog/224423197601"
    assert post.title == "연말정산 & 세금 안내"
    assert "첫 번째 문장" in post.content
    assert "ignored" not in post.content
    assert post.description == "공개 글 설명 & 요약"
    assert post.image_url == "https://example.com/naver-cover.jpg"
    assert post.tags == ["연말정산", "세금&절세"]
    assert post.published_at == datetime.fromtimestamp(1790409702.864, UTC)


def test_rejects_invalid_blog_id_and_non_numeric_log_no() -> None:
    with pytest.raises(ValueError, match="invalid Naver blog ID"):
        NaverSource("education/blog")

    source = NaverSource("education_blog")
    with pytest.raises(ValueError, match="invalid Naver logNo"):
        source._log_no_from_url("https://blog.naver.com/education_blog/not-a-number")


@pytest.mark.parametrize(
    ("html", "message"),
    [
        (
            '<meta property="og:title" content="제목"><script>addDate="1790409702864";</script>',
            "article body not found",
        ),
        (
            '<meta property="og:title" content="제목"><div class="se-main-container">본문</div>',
            "published date not found",
        ),
    ],
)
def test_missing_body_or_date_is_an_explicit_error(html: str, message: str) -> None:
    source = NaverSource("education_blog")
    with pytest.raises(ValueError, match=message):
        source.parse(html, "https://blog.naver.com/education_blog/123")
