"""_posts_index.md thumb URL 일괄 갱신 — CDN 서명 URL 만료 시 연 1회 실행 (매년 6월 권장)"""
import re
import time
import requests
from pathlib import Path

INDEX = Path("_posts_index.md")
UA = {"User-Agent": "Mozilla/5.0"}
DELAY = 1.5  # 서버 과부하 방지


def get_og_image(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=12, headers=UA)
        if r.status_code != 200:
            return None
        for pat in [
            r'property="og:image"\s+content="([^"]+)"',
            r'content="([^"]+)"\s+property="og:image"',
        ]:
            m = re.search(pat, r.text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def main():
    text = INDEX.read_text(encoding="utf-8")
    lines = text.splitlines()
    result = []
    i = 0
    updated = 0
    failed = 0

    # url: 줄 위치 기억 후 가까운 thumb: 줄 탐색 (category: 등이 사이에 있을 수 있음)
    pending_url: str | None = None
    while i < len(lines):
        line = lines[i]
        url_match = re.match(r"^- url: (https://j2gblog\.tistory\.com/\S+)", line)
        if url_match:
            pending_url = url_match.group(1)
            result.append(line)
            i += 1
            continue
        if pending_url and line.startswith("- thumb:"):
            old_thumb = line
            new_url = get_og_image(pending_url)
            if new_url:
                result.append(f"- thumb: {new_url}")
                if new_url not in old_thumb:
                    print(f"  갱신: {pending_url}")
                    updated += 1
                else:
                    print(f"  동일: {pending_url}")
            else:
                print(f"  실패(원본 유지): {pending_url}")
                result.append(old_thumb)
                failed += 1
            time.sleep(DELAY)
            pending_url = None
            i += 1
            continue
        # url 블록 범위를 벗어나면 pending 초기화 (### 새 항목 시작 등)
        if line.startswith("###") or line.startswith("---"):
            pending_url = None
        result.append(line)
        i += 1

    INDEX.write_text("\n".join(result) + "\n", encoding="utf-8")
    print(f"\n완료: {updated}개 갱신, {failed}개 실패")


if __name__ == "__main__":
    main()
