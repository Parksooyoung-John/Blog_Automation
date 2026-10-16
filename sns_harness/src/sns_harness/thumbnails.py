from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


class ThumbnailError(ValueError):
    """Raised when a numbered thumbnail cannot be safely published."""


@dataclass(frozen=True)
class ThumbnailResolution:
    number: int
    filename: str
    path: Path
    public_url: str = ""


class ThumbnailResolver:
    def __init__(
        self, directory: Path, repository: str, ref: str = "main",
        asset_path: str = "assets/naver_img", *, timeout: float = 20,
        session: requests.Session | None = None
    ) -> None:
        self.directory = directory
        self.repository = repository
        self.ref = ref
        self.asset_path = asset_path
        self.timeout = timeout
        self.session = session

    def resolve(self, number: int | None) -> ThumbnailResolution:
        if number is None:
            raise ThumbnailError("게시번호가 없습니다.")
        result = resolve_thumbnail(number, self.directory)
        return ThumbnailResolution(
            result.number,
            result.filename,
            result.path,
            build_public_url(self.repository, self.ref, self.asset_path, result.filename),
        )

    def verify(self, url: str) -> None:
        verify_public_url(url, session=self.session, timeout=self.timeout)


def resolve_thumbnail(number: int, directory: Path) -> ThumbnailResolution:
    if number < 1:
        raise ThumbnailError("게시번호는 1 이상의 숫자여야 합니다.")
    if not directory.is_dir():
        raise ThumbnailError(f"썸네일 폴더가 없습니다: {directory}")
    prefix = f"{number}_썸네일."
    candidates = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.name.lower().startswith(prefix.lower())
    )
    if not candidates:
        raise ThumbnailError(f"게시번호 {number}에 맞는 썸네일이 없습니다.")
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise ThumbnailError(f"게시번호 {number}에 썸네일이 여러 개입니다: {names}")
    if candidates[0].suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ThumbnailError(f"지원하지 않는 썸네일 확장자입니다: {candidates[0].suffix}")
    return ThumbnailResolution(number, candidates[0].name, candidates[0])


def build_public_url(repository: str, ref: str, asset_path: str, filename: str) -> str:
    if not repository:
        raise ThumbnailError("GITHUB_REPOSITORY가 설정되지 않았습니다.")
    raw_parts = [part for part in asset_path.strip("/").split("/") if part]
    raw_parts.append(filename)
    encoded_path = "/".join(quote(part, safe="") for part in raw_parts)
    return f"https://raw.githubusercontent.com/{repository}/{quote(ref, safe='')}/{encoded_path}"


def verify_public_url(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 20,
) -> None:
    client = session or requests.Session()
    response = client.head(url, allow_redirects=True, timeout=timeout)
    if response.status_code < 200 or response.status_code >= 300:
        raise ThumbnailError(f"썸네일 공개 URL 확인 실패: HTTP {response.status_code}")
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and not content_type.startswith("image/"):
        raise ThumbnailError(f"공개 URL이 이미지가 아닙니다: {content_type}")
