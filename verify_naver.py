"""발행된 네이버 글 점검 — 원고대로, 규칙대로 올라갔는지 라이브에서 확인한다.

원고 검수(check_naver.py)는 파일만 본다. 카테고리 오배정·발행 간격·태그 중복처럼
발행할 때 생기는 문제는 라이브를 봐야 잡힌다. 실제로 2편이 근로장려금 카테고리에
들어간 것도, 하루에 3편을 올린 것도 여기서 발견했다(2026-09-26).

    python -X utf8 verify_naver.py            # 최근 글 전체
    python -X utf8 verify_naver.py 224423197601
"""
import datetime
import re
import sys
from collections import Counter, defaultdict

import requests

BLOG = "education_blog"
UA = {"User-Agent": "Mozilla/5.0", "Referer": f"https://m.blog.naver.com/{BLOG}"}

# 제목 키워드 → 들어가야 할 카테고리. 위에서부터 먼저 맞는 것을 쓴다.
CATEGORY_RULES = [
    (["근로장려금", "자녀장려금", "장려금"], "근로장려금·자녀장려금"),
    (["실업급여", "구직급여", "고용보험", "퇴사"], "실업급여·고용보험"),
    (["연말정산", "종합소득세", "재산세", "자동차세", "부가세"], "연말정산·세금"),
    (["국민연금", "건강보험", "연금"], "연금·건강보험"),
]
MAX_SHARED_TAGS = 3


def _get(url):
    return requests.get(url, headers=UA, timeout=15)


def categories() -> list:
    u = f"https://m.blog.naver.com/api/blogs/{BLOG}/category-list"
    return _get(u).json()["result"]["mylogCategoryList"]


def recent(n=10) -> list:
    u = f"https://m.blog.naver.com/api/blogs/{BLOG}/post-list?categoryNo=0&itemCount={n}&page=1"
    out = []
    for i in _get(u).json()["result"]["items"]:
        kst = datetime.datetime.fromtimestamp(int(i["addDate"]) / 1000, datetime.UTC) \
            + datetime.timedelta(hours=9)
        out.append({"logNo": str(i["logNo"]),
                    "title": i.get("title") or i.get("titleWithInspectMessage") or "",
                    "category": i.get("categoryName") or "",
                    "when": kst})
    return out


def expected_category(title: str) -> str:
    for words, name in CATEGORY_RULES:
        if any(w in title for w in words):
            return name
    return ""


def inspect(log_no: str) -> dict:
    html = _get(f"https://m.blog.naver.com/{BLOG}/{log_no}").text
    i = html.find("se-main-container")
    j = html.find("{&#034;title&#034;", i)
    body = html[i:j] if j > i else html[i:i + 60000]

    text = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").replace("​", "")
    text = re.sub(r"\s+", " ", text).strip()

    # 실제 태그는 gsTagName. baLogData의 "tagNames"는 추적용이라 늘 비어 있다
    # (1편 점검 때 이걸 읽고 "태그 없음"으로 오판했다).
    m = re.search(r'var gsTagName = "([^"]*)"', html)
    tags = [t for t in (m.group(1).split(",") if m and m.group(1) else []) if t]

    return {
        "chars": len(text),
        "images": len(re.findall(r'se-component se-image[ "]', body)),
        "subheads": len(re.findall(r'se-component se-quotation[ "]', body)),
        "tags": tags,
        "inlinks": len(re.findall(rf"blog\.naver\.com/{BLOG}/\d+", body)),
        "tistory": len(re.findall(r"j2gblog\.tistory\.com", body)),
    }


def title_shape(title: str) -> str:
    """제목 구조 지문 — 쉼표 유무 + 마지막 어절(종결)."""
    tail = title.replace("?", "").split()[-1]
    return ("쉼표+" if "," in title else "") + tail


def main(argv):
    posts = recent()
    if argv:
        posts = [p for p in posts if p["logNo"] in argv] or [
            {"logNo": a, "title": "", "category": "", "when": None} for a in argv]

    data = {p["logNo"]: inspect(p["logNo"]) for p in posts}
    problems = []

    for p in posts:
        r = data[p["logNo"]]
        print(f"\n{p['logNo']}  {p['title']}")
        if p["when"]:
            print(f"  발행 {p['when']:%Y-%m-%d %H:%M}  |  카테고리 {p['category']}")
        print(f"  {r['chars']}자 / 이미지 {r['images']} / 소제목 {r['subheads']} "
              f"/ 태그 {len(r['tags'])} / 내부링크 {r['inlinks']}")

        if not r["tags"]:
            problems.append(f"{p['logNo']} 태그가 비어 있다")
        if r["images"] < 2:
            problems.append(f"{p['logNo']} 이미지가 {r['images']}장 (최소 2장)")
        if not 800 <= r["chars"] <= 1800:
            problems.append(f"{p['logNo']} 분량 {r['chars']}자 (800~1800)")
        if r["tistory"]:
            problems.append(f"{p['logNo']} 티스토리 링크가 있다 — 유입을 내보내고 유사문서 위험")
        if r["inlinks"] == 0:
            problems.append(f"{p['logNo']} 내부 링크가 없다 (맥락 링크 1개 권장)")

        want = expected_category(p["title"])
        if want and p["category"] and want != p["category"]:
            problems.append(f"{p['logNo']} 카테고리가 '{p['category']}' — '{want}'로 가야 한다")

    # 글끼리 비교해야 보이는 것들
    by_day = defaultdict(list)
    for p in posts:
        if p["when"]:
            by_day[p["when"].date()].append(p["logNo"])
    for day, ids in by_day.items():
        if len(ids) > 1:
            problems.append(f"{day}에 {len(ids)}편 발행 — 하루 1편 이내")

    for shape, ids in Counter(title_shape(p["title"]) for p in posts if p["title"]).items():
        if ids > 1:
            problems.append(f"제목 구조 '{shape}'가 {ids}편에서 반복된다")

    for a in posts:
        for b in posts:
            if a["logNo"] >= b["logNo"]:
                continue
            shared = set(data[a["logNo"]]["tags"]) & set(data[b["logNo"]]["tags"])
            if len(shared) > MAX_SHARED_TAGS:
                problems.append(
                    f"{a['logNo']}·{b['logNo']} 공통 태그 {len(shared)}개 "
                    f"({MAX_SHARED_TAGS}개 이하 권장): {' '.join(sorted(shared))}")

    print("\n" + "=" * 60)
    if problems:
        print(f"확인 필요 {len(problems)}건")
        for x in problems:
            print("  ⚠", x)
    else:
        print("전체 통과")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
