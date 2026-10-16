from pathlib import Path

import pytest

from sns_harness.thumbnails import ThumbnailError, build_public_url, resolve_thumbnail


def test_resolves_numbered_thumbnail() -> None:
    result = resolve_thumbnail(17, Path("../assets/naver_img"))
    assert result.filename == "17_썸네일.png"
    assert result.path.name == "17_썸네일.png"


def test_missing_thumbnail_is_blocked() -> None:
    missing = Path("this-directory-does-not-exist")
    with pytest.raises(ThumbnailError, match="없습니다"):
        resolve_thumbnail(17, missing)


def test_public_url_preserves_asset_path() -> None:
    url = build_public_url("owner/repo", "main", "assets/naver_img", "17_썸네일.png")
    assert url == (
        "https://raw.githubusercontent.com/owner/repo/main/assets/naver_img/"
        "17_%EC%8D%B8%EB%84%A4%EC%9D%BC.png"
    )
