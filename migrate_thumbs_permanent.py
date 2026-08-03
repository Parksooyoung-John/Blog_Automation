"""내부 링크 카드 썸네일을 영구(jsdelivr) 호스팅으로 일괄 마이그레이션 — 1회성 도구.

_posts_index.md의 현재 thumb: URL(Tistory 서명 URL, 정상 상태)을 한 번씩
다운로드해 assets/thumbnails/{numeric_id}.jpg로 저장하고, 인덱스의 thumb: 필드를
jsdelivr 영구 URL로 교체한다. 이어서 각 포스트의 라이브 본문에서 "함께 읽으면
좋은 글" 카드 이미지(daumcdn 서명 URL)를 새 영구 URL로 교체해 enhanced_{id}.html
패치 파일을 생성한다 — update_posts.py로 라이브 재발행하면 매달 반복되던
썸네일 만료 문제가 이후 발행분부터 사라진다.

Usage: python -X utf8 migrate_thumbs_permanent.py
"""
import re
import time
from pathlib import Path

from refresh_thumbs import fetch, resolve_numeric_id, extract_body
from thumb_host import host_thumb

BASE = Path(__file__).parent
WS = BASE / "_workspace"
INDEX_PATH = BASE / "_posts_index.md"


def patch_thumbs_permanent(body: str, fresh_map: dict) -> tuple[str, int]:
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
        if not fresh:
            return m.group(0)
        count += 1
        return f'href="https://j2gblog.tistory.com/{target_id}"{pre}src="{fresh}"'

    new_body = pattern.sub(repl, body)
    return new_body, count


def main():
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    entries = re.findall(r"- url: (\S+)\n- category: (.+?)\n- thumb: (\S+)", index_text)
    print(f"인덱스 포스트 {len(entries)}개 발견")

    id_map: dict[str, str] = {}
    body_cache: dict[str, str] = {}
    fresh_map: dict[str, str] = {}

    for i, (url, category, thumb) in enumerate(entries, 1):
        text = fetch(url)
        if text is None:
            print(f"  [{i}/{len(entries)}] 접근 실패: {url}")
            continue
        nid = resolve_numeric_id(url, text)
        if nid is None:
            print(f"  [{i}/{len(entries)}] 숫자ID 해석 실패: {url}")
            continue
        id_map[url] = nid
        body_cache[nid] = text

        permanent = host_thumb(nid, thumb)
        if permanent:
            fresh_map[nid] = permanent
            print(f"  [{i}/{len(entries)}] OK /{nid}")
        else:
            print(f"  [{i}/{len(entries)}] 다운로드 실패, 기존 thumb 유지: /{nid}")
        time.sleep(0.1)

    print(f"\n영구 호스팅 완료: {len(fresh_map)}/{len(entries)}")

    def repl_thumb(m):
        url, category = m.group(1), m.group(2)
        nid = id_map.get(url)
        if nid and nid in fresh_map:
            return f"- url: {url}\n- category: {category}\n- thumb: {fresh_map[nid]}"
        return m.group(0)

    new_index = re.sub(
        r"- url: (\S+)\n- category: (.+?)\n- thumb: \S+",
        repl_thumb, index_text,
    )
    INDEX_PATH.write_text(new_index, encoding="utf-8")
    print("_posts_index.md thumb 필드 전체 영구 URL로 교체 완료")

    patched = []
    for url, nid in id_map.items():
        text = body_cache[nid]
        body = extract_body(text)
        if body is None:
            continue
        new_body, n = patch_thumbs_permanent(body, fresh_map)
        if n > 0:
            (WS / f"enhanced_{nid}.html").write_text(new_body, encoding="utf-8")
            patched.append((nid, n))

    print(f"\n카드 이미지 교체 필요 포스트: {len(patched)}개")
    if patched:
        ids_str = ", ".join(nid for nid, _ in sorted(patched, key=lambda x: int(x[0])))
        print("\n다음 ID를 update_posts.py의 UPDATE_POSTS에 넣고 실행하면 라이브 재발행까지 완료됩니다:")
        print(f"[{ids_str}]")


if __name__ == "__main__":
    main()
