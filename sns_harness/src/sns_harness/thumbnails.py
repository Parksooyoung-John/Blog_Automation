from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


CARD_MIN, CARD_MAX = 2, 10   # Threads carousels take 2-20 items; 10 keeps the Notion URL list short
MAX_IMAGE_BYTES = 8 * 1024 * 1024   # Threads image limit


class ThumbnailError(ValueError):
    """Raised when a numbered thumbnail cannot be safely published."""


@dataclass(frozen=True)
class CardNewsResolution:
    number: int
    filenames: tuple[str, ...]
    paths: tuple[Path, ...]
    public_urls: tuple[str, ...] = ()


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

    def resolve_cards(self, number: int | None) -> CardNewsResolution:
        if number is None:
            raise ThumbnailError("게시번호가 없습니다.")
        result = resolve_card_news(number, self.directory)
        urls = tuple(
            build_public_url(self.repository, self.ref, self.asset_path, name)
            for name in result.filenames
        )
        return CardNewsResolution(result.number, result.filenames, result.paths, urls)

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


def resolve_card_news(number: int, directory: Path) -> CardNewsResolution:
    """Find `{number}_카드뉴스_{k}.png|jpg` for k = 1..n. Slide 1 is the cover."""
    if number < 1:
        raise ThumbnailError("게시번호는 1 이상의 숫자여야 합니다.")
    if not directory.is_dir():
        raise ThumbnailError(f"카드뉴스 폴더가 없습니다: {directory}")
    pattern = re.compile(rf"^{number}_카드뉴스_(\d+)\.(png|jpe?g)$", re.IGNORECASE)
    found: dict[int, Path] = {}
    for path in sorted(directory.iterdir()):
        match = pattern.match(path.name) if path.is_file() else None
        if not match:
            continue
        index = int(match.group(1))
        if index in found:
            raise ThumbnailError(
                f"카드뉴스 {index}번이 여러 개입니다: {found[index].name}, {path.name}"
            )
        found[index] = path
    if not found:
        raise ThumbnailError(f"게시번호 {number}에 맞는 카드뉴스가 없습니다.")
    if sorted(found) != list(range(1, len(found) + 1)):
        raise ThumbnailError(
            f"카드뉴스 번호가 1부터 이어지지 않습니다: {sorted(found)}"
        )
    if not CARD_MIN <= len(found) <= CARD_MAX:
        raise ThumbnailError(
            f"카드뉴스는 {CARD_MIN}~{CARD_MAX}장이어야 합니다: {len(found)}장"
        )
    paths = tuple(found[index] for index in sorted(found))
    for path in paths:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise ThumbnailError(f"카드뉴스 이미지가 8MB를 넘습니다: {path.name}")
    return CardNewsResolution(number, tuple(path.name for path in paths), paths)


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
