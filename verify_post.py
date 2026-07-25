"""발행 직후 라이브 페이지 점검 — update_posts.py와 03_tistory_playwright.py가 공용으로 쓴다.

오늘(2026-07-17) 순서대로 발견된 4개 버그를 자동으로 잡기 위한 것:
1. 최종 업데이트/면책 블록쿼트가 통째로 사라짐
2. 메타 디스크립션·키워드 등 내부용 필드가 본문에 그대로 노출됨
3. 내부링크 카드 이미지 URL이 잘못 기재돼 404
4. 제목에 쉼표·물음표가 있으면 Tistory가 슬러그에서 해당 문자를 제거해
   발행 패널이 보여준 URL과 실제 라이브 URL이 달라짐(SOXL, 재산세, 부가세에서 확인)

발행 스크립트를 막지는 않는다 — 문제 발견 시 콘솔에 경고만 출력해 사람이 바로 알아채게 한다.
"""
import html as ihtml
import re

import requests

UA = {"User-Agent": "Mozilla/5.0"}
META_LEAK_MARKERS = ["메타 디스크립션", "예상 읽기 시간"]


def _strip_slug_punctuation(url: str) -> str:
    """Tistory가 슬러그 생성 시 제거하는 문자(쉼표·물음표 등)를 제거한 대체 URL."""
    return re.sub(r"[,?]", "", url)


def verify_live_post(url: str) -> list[str]:
    """발행된 글 URL을 점검해 문제 목록을 반환한다 (빈 리스트면 이상 없음)."""
    problems = []
    try:
        r = requests.get(url, timeout=15, headers=UA)
    except Exception as e:
        return [f"페이지 접근 실패: {e}"]

    if r.status_code == 404:
        alt = _strip_slug_punctuation(url)
        if alt != url:
            try:
                r2 = requests.get(alt, timeout=15, headers=UA)
                if r2.status_code == 200:
                    problems.append(f"URL 슬러그 불일치 — 실제 라이브 URL: {alt}")
                    r = r2
                else:
                    return [f"HTTP {r.status_code} (대체 URL도 {r2.status_code})"]
            except Exception as e:
                return [f"HTTP {r.status_code} (대체 URL 확인 실패: {e})"]
        else:
            return [f"HTTP {r.status_code}"]
    elif r.status_code != 200:
        return [f"HTTP {r.status_code}"]

    for marker in META_LEAK_MARKERS:
        if marker in r.text:
            problems.append(f"메타 필드 노출: '{marker}'")

    if "<blockquote" not in r.text:
        problems.append("공지·면책 블록쿼트 없음")

    imgs = re.findall(r'<img[^>]+src="([^"]+)"', r.text)
    imgs = [ihtml.unescape(u) for u in imgs if "thumb/R800x0" in u]
    for u in imgs[:6]:  # 카드 이미지만 확인 — 과도한 요청 방지
        try:
            rr = requests.get(u, timeout=8, headers=UA)
            if rr.status_code != 200 or "image" not in rr.headers.get("Content-Type", ""):
                problems.append(f"카드 이미지 로드 실패: {u[:70]}")
        except Exception:
            problems.append(f"카드 이미지 확인 실패: {u[:70]}")

    return problems


def print_verify_result(label: str, url: str) -> None:
    problems = verify_live_post(url)
    if problems:
        print(f"  ⚠️ [{label}] 발행 후 점검 문제 {len(problems)}건:")
        for p in problems:
            print(f"     - {p}")
    else:
        print(f"  ✅ [{label}] 발행 후 점검 통과")
