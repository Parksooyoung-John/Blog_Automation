"""내부 링크 카드 썸네일(Tistory og:image 서명 URL) 만료 점검·복구 도구.

배경: img1.daumcdn.net 프록시 URL은 credential/expires/signature 서명이 걸려 있고
발급 후 약 1개월이면 만료된다. _posts_index.md의 thumb 필드와, 이미 발행된 포스트
본문에 박제된 카드 이미지 모두 이 문제의 영향을 받는다.

동작:
1. _posts_index.md의 모든 포스트에서 최신 og:image를 재수집해 만료 여부와 무관하게 갱신
   (슬러그 URL 포스트는 페이지 소스의 entryId로 숫자 게시글 ID를 해석)
2. 각 포스트의 라이브 본문에서 "함께 읽으면 좋은 글" 카드 이미지 중 만료된(daumcdn) 것을
   최신 URL로 교체 → 교체가 발생한 포스트만 _workspace/enhanced_{id}.html 로 저장
3. 카드 이미지 교체가 필요했던 포스트 ID 목록을 출력 — 이 목록을 update_posts.py의
   UPDATE_POSTS에 넣고 실행하면 실제 라이브 재발행까지 완료된다.

Usage:
    python -X utf8 refresh_thumbs.py            # 점검 + 인덱스 갱신 + 패치 파일 생성
    python -X utf8 refresh_thumbs.py --check     # 만료 현황만 리포트 (파일 변경 없음)
"""
import argparse
import html as ihtml
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path(__file__).parent
WS = BASE / "_workspace"
INDEX_PATH = BASE / "_posts_index.md"
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=15, headers=UA)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"  ⚠️ fetch 실패 {url}: {e}")
    return None


def resolve_numeric_id(url: str, text: str) -> str | None:
    """숫자 URL이면 그대로, 슬러그(entry/제목)면 entryId 필드에서 추출."""
    m = re.search(r"tistory\.com/(\d+)$", url)
    if m:
        return m.group(1)
    m = re.search(r'"entryId":(\d+)', text)
    return m.group(1) if m else None


def fetch_og_image(text: str) -> str | None:
    m = re.search(r'property="og:image"\s+content="([^"]+)"', text)
    if not m:
        m = re.search(r'content="([^"]+)"\s+property="og:image"', text)
    return ihtml.unescape(m.group(1)) if m else None


def thumb_expiry(thumb_url: str) -> datetime | None:
    m = re.search(r"expires%3D(\d+)|expires=(\d+)", thumb_url)
    if not m:
        return None
    ts = int(m.group(1) or m.group(2))
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def extract_body(text: str) -> str | None:
    m = re.search(
        r'<div class="tt_article_useless_p_margin contents_style">(.*?)</div>\s*(?:<div class="container_postbtn|<!--)',
        text, re.DOTALL,
    )
    if not m:
        m = re.search(r'(<div class="tt_article_useless_p_margin[^>]*>.*)', text, re.DOTALL)
    return m.group(1) if m else None


def patch_thumbs(body: str, fresh_map: dict) -> tuple[str, int]:
    """카드 <a href=".../N"> 다음에 오는 <img src="...daumcdn..."> 를 fresh_map[N]으로 교체."""
    count = 0
    pattern = re.compile(
        r'href="https://j2gblog\.tistory\.com/(\d+)"(.{0,400}?)src="([^"]+)"',
        re.DOTALL,
    )

    def repl(m):
        nonlocal count
        target_id, pre, old_src = m.group(1), m.group(2), m.group(3)
        if "daumcdn" not in old_src:
            return m.group(0)
        fresh = fresh_map.get(target_id)
        old_unescaped = ihtml.unescape(old_src)
        if not fresh or fresh == old_unescaped:
            return m.group(0)
        count += 1
        return f'href="https://j2gblog.tistory.com/{target_id}"{pre}src="{ihtml.escape(fresh, quote=True)}"'

    new_body = pattern.sub(repl, body)
    return new_body, count


def check_only(index_text: str) -> None:
    entries = re.findall(r"- url: (\S+)\n- category: .+?\n- thumb: (\S+)", index_text)
    now = datetime.now(tz=timezone.utc)
    expired, soon, ok = [], [], []
    for url, thumb in entries:
        exp = thumb_expiry(thumb)
        if exp is None:
            continue
        days_left = (exp - now).days
        if days_left < 0:
            expired.append((url, days_left))
        elif days_left < 7:
            soon.append((url, days_left))
        else:
            ok.append((url, days_left))
    print(f"만료됨: {len(expired)}개 / 7일 이내 만료 예정: {len(soon)}개 / 정상: {len(ok)}개")
    for url, days in expired[:10]:
        print(f"  ❌ {days}일 초과 만료: {url}")
    for url, days in soon[:10]:
        print(f"  ⚠️ {days}일 후 만료: {url}")


def main():
    parser = argparse.ArgumentParser(description="내부 링크 카드 썸네일 만료 점검·복구")
    parser.add_argument("--check", action="store_true", help="만료 현황만 리포트 (파일 변경 없음)")
    args = parser.parse_args()

    index_text = INDEX_PATH.read_text(encoding="utf-8")

    if args.check:
        check_only(index_text)
        return

    entries = re.findall(r"### (.+?)\n- url: (\S+)\n", index_text)
    print(f"인덱스 포스트 {len(entries)}개 발견")

    id_map: dict[str, str] = {}
    body_cache: dict[str, str] = {}
    fresh_map: dict[str, str] = {}

    for i, (title, url) in enumerate(entries, 1):
        text = fetch(url)
        if text is None:
            print(f"  [{i}/{len(entries)}] ❌ 접근 실패: {url}")
            continue
        nid = resolve_numeric_id(url, text)
        if nid is None:
            print(f"  [{i}/{len(entries)}] ⚠️ 숫자ID 해석 실패: {url}")
            continue
        id_map[url] = nid
        body_cache[nid] = text
        og = fetch_og_image(text)
        if og:
            fresh_map[nid] = og
        print(f"  [{i}/{len(entries)}] /{nid}  og={'OK' if og else 'NONE'}  {title[:35]}")
        time.sleep(0.15)

    print(f"\n숫자ID 해석 완료: {len(id_map)}/{len(entries)}, fresh OG 확보: {len(fresh_map)}개")

    def repl_thumb(m):
        url = m.group(1)
        nid = id_map.get(url)
        if nid and nid in fresh_map:
            return f"- url: {url}\n- category: {m.group(2)}\n- thumb: {fresh_map[nid]}"
        return m.group(0)

    new_index = re.sub(
        r"- url: (\S+)\n- category: (.+?)\n- thumb: \S+",
        repl_thumb, index_text,
    )
    INDEX_PATH.write_text(new_index, encoding="utf-8")
    print("✅ _posts_index.md thumb 필드 전체 갱신 완료")

    patched = []
    for url, nid in id_map.items():
        text = body_cache[nid]
        body = extract_body(text)
        if body is None:
            continue
        new_body, n = patch_thumbs(body, fresh_map)
        if n > 0:
            (WS / f"enhanced_{nid}.html").write_text(new_body, encoding="utf-8")
            patched.append((nid, n))

    print(f"\n✅ 카드 이미지 교체 필요 포스트: {len(patched)}개")
    for nid, n in patched:
        print(f"  /{nid}: {n}개 카드 이미지 교체")

    if patched:
        ids_str = ", ".join(nid for nid, _ in sorted(patched, key=lambda x: int(x[0])))
        print(f"\n다음 ID를 update_posts.py의 UPDATE_POSTS에 넣고 실행하면 라이브 재발행까지 완료됩니다:")
        print(f"[{ids_str}]")


if __name__ == "__main__":
    main()
