"""내부 링크 카드 썸네일 영구 호스팅 — GitHub + jsdelivr CDN.

배경: Tistory og:image(daumcdn 프록시) URL은 credential/expires/signature로
서명되어 있고 계정 단위로 약 1개월마다 일괄 만료된다(리사이즈 변형 포함 예외 없음).
매달 전체 포스트를 재발행해야 하는 문제를 근본적으로 없애기 위해, 카드 썸네일을
한 번 다운로드해 이 저장소(public repo)에 커밋하고 jsdelivr CDN으로 서빙한다.
jsdelivr는 public GitHub repo의 파일을 무료로 영구 캐싱 서빙한다 — 만료 없음.

Usage (다른 스크립트에서 import):
    from thumb_host import host_thumb
    permanent_url = host_thumb("149", og_image_url)
"""
import re
from pathlib import Path

import requests
from PIL import Image
from io import BytesIO

GITHUB_REPO = "Parksooyoung-John/Blog_Automation"
GITHUB_BRANCH = "main"
ASSETS_DIR = Path(__file__).parent / "assets" / "thumbnails"
MAX_WIDTH = 800
JPEG_QUALITY = 82
UA = {"User-Agent": "Mozilla/5.0"}


def jsdelivr_url(post_id: str) -> str:
    return f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GITHUB_BRANCH}/assets/thumbnails/{post_id}.jpg"


def host_thumb(post_id: str, source_url: str) -> str | None:
    """source_url 이미지를 다운로드해 assets/thumbnails/{post_id}.jpg로 저장하고
    jsdelivr 영구 URL을 반환한다. 실패 시 None."""
    try:
        r = requests.get(source_url, timeout=20, headers=UA)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"  ⚠️ 다운로드/디코딩 실패 ({post_id}): {e}")
        return None

    if img.width > MAX_WIDTH:
        new_height = int(img.height * MAX_WIDTH / img.width)
        img = img.resize((MAX_WIDTH, new_height), Image.LANCZOS)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ASSETS_DIR / f"{post_id}.jpg"
    img.save(out_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return jsdelivr_url(post_id)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python thumb_host.py <post_id> <source_image_url>")
        sys.exit(1)
    url = host_thumb(sys.argv[1], sys.argv[2])
    print(url or "실패")
