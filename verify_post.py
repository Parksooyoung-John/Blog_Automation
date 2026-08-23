"""발행 직후 라이브 페이지 점검 — update_posts.py와 03_tistory_playwright.py가 공용으로 쓴다.

오늘(2026-07-17) 순서대로 발견된 4개 버그를 자동으로 잡기 위한 것:
1. 최종 업데이트/면책 블록쿼트가 통째로 사라짐
2. 메타 디스크립션·키워드 등 내부용 필드가 본문에 그대로 노출됨
3. 내부링크 카드 이미지 URL이 잘못 기재돼 404
4. 제목에 쉼표·물음표가 있으면 Tistory가 슬러그에서 해당 문자를 제거해
   발행 패널이 보여준 URL과 실제 라이브 URL이 달라짐(SOXL, 재산세, 부가세에서 확인)

2026-08-22 추가로 발견·수정된 2개 결함:
5. **카드 이미지 검증 사각지대**: 3번 해결책이 "thumb/R800x0"(구 daumcdn 프록시) 패턴만
   찾았는데, 2026-08-03 thumb_host.py 도입 이후 카드 이미지는 전부 jsdelivr CDN URL로
   바뀌었다. 즉 이 함수가 몇 주간 카드 이미지를 사실상 전혀 검사하지 않고 있었다
   (필터에 안 걸려 imgs가 항상 빈 리스트). 두 패턴을 모두 인식하도록 수정.
6. 제목에 `%`(퍼센트) 기호가 있으면 슬러그에서 제거돼 쉼표·물음표와 같은 문제가
   발생한다("10% 안 갚으면" → URL은 "10%-안-갚으면"). `_strip_slug_punctuation`에 추가.

발행 스크립트를 막지는 않는다 — 문제 발견 시 콘솔에 경고만 출력해 사람이 바로 알아채게 한다.
"""
import html as ihtml
import re

import requests

UA = {"User-Agent": "Mozilla/5.0"}
META_LEAK_MARKERS = ["메타 디스크립션", "예상 읽기 시간"]


def _strip_slug_punctuation(url: str) -> str:
    """Tistory가 슬러그 생성 시 제거하는 문자(쉼표·물음표·퍼센트 등)를 제거한 대체 URL."""
    return re.sub(r"[,?%]", "", url)


def _check_search_snippet(page_html: str) -> list[str]:
    """구글 검색결과에 실제로 노출되는 설명문을 점검한다.

    Tistory는 blog-writer가 쓴 메타 디스크립션을 쓰지 않고 **본문 앞부분을 잘라**
    description/og:description을 만든다. 따라서 도입부 첫 문장이 곧 검색결과 설명문이다.
    2026-08-23 실측에서 공지 블록쿼트가 설명문에 그대로 찍힌 글(/83)이 발견됐는데,
    42노출·7.98위인데 클릭이 0이었다. 이 함수는 그 유형을 발행 직후 잡는다.
    """
    m = re.search(r'<meta name="description" content="([^"]*)"', page_html)
    if not m:
        return ["검색결과 설명문(description) 태그 없음"]

    desc = ihtml.unescape(m.group(1))
    head = desc[:120]
    out = []

    if "📅" in desc[:200] or "최종 업데이트" in desc[:200]:
        out.append("검색결과 설명문에 공지 블록 노출 — 공지를 본문 맨 아래(v3)로 옮길 것")
    if not re.search(r"\d", head):
        out.append("검색결과 설명문 앞 120자에 숫자가 없음 — 도입부에 구체 수치 배치 권장")
    return out


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

    problems.extend(_check_search_snippet(r.text))

    # 카드 이미지 URL 패턴: "thumb/R800x0"(구 daumcdn 프록시, 만료됨) 또는
    # jsdelivr 영구 CDN(2026-08-03 thumb_host.py 도입 이후 표준). 하나만 검사하면
    # 다른 쪽으로 이미 전환된 사이트에서는 카드 이미지가 검증 대상에서 통째로 빠진다.
    imgs = re.findall(r'<img[^>]+src="([^"]+)"', r.text)
    imgs = [ihtml.unescape(u) for u in imgs
            if "thumb/R800x0" in u or "cdn.jsdelivr.net" in u and "thumbnails" in u]
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
