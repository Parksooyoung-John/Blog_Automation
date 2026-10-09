"""발행된 네이버 글 점검 — 원고대로, 규칙대로 올라갔는지 라이브에서 확인한다.

원고 검수(check_naver.py)는 파일만 본다. 카테고리 오배정·발행 간격·태그 중복처럼
발행할 때 생기는 문제는 라이브를 봐야 잡힌다. 실제로 2편이 근로장려금 카테고리에
들어간 것도, 하루에 3편을 올린 것도 여기서 발견했다(2026-09-26).

    python -X utf8 verify_naver.py            # 최근 글 전체
    python -X utf8 verify_naver.py 224423197601
    python -X utf8 verify_naver.py --selftest
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
# 서식 기준. AI 브리핑에 인용된 블로그 글 24편 중 글자 16이 13편, 왼쪽 정렬이 19편이었고 우리 글도 전부 그렇다.
BODY_FONT = "16"
MAX_CENTER_PCT = 10


def _get(url):
    return requests.get(url, headers=UA, timeout=15)


def categories() -> list:
    u = f"https://m.blog.naver.com/api/blogs/{BLOG}/category-list"
    return _get(u).json()["result"]["mylogCategoryList"]


def recent(n=10, page=1) -> list:
    u = f"https://m.blog.naver.com/api/blogs/{BLOG}/post-list?categoryNo=0&itemCount={n}&page={page}"
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
    return parse(_get(f"https://m.blog.naver.com/{BLOG}/{log_no}").text)


def parse(html: str) -> dict:
    # 본문은 se-main-container부터 마지막 se-component 뒤 첫 <script> 앞까지다.
    # 전에는 본문 뒤의 `{&#034;title&#034;` 표지로 끊었는데 2026-10-07에 그 표지가 사라져서
    # 뒤따르는 스크립트 6만 자가 본문으로 세어졌다(10편 1,400자를 12,994자로 보고).
    i = html.find("se-main-container")
    comps = [m.start() for m in re.finditer(r"se-component se-", html)]
    if i < 0 or not comps:
        raise ValueError("본문(se-main-container·se-component)을 찾지 못했다 — 네이버 마크업이 바뀌었을 수 있다")
    j = html.find("<script", comps[-1])
    body = html[i:j] if j > i else html[i:]

    text = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").replace("​", "")
    text = re.sub(r"\s+", " ", text).strip()

    # 실제 태그는 gsTagName. baLogData의 "tagNames"는 추적용이라 늘 비어 있다
    # (1편 점검 때 이걸 읽고 "태그 없음"으로 오판했다).
    m = re.search(r'var gsTagName = "([^"]*)"', html)
    tags = [t for t in (m.group(1).split(",") if m and m.group(1) else []) if t]

    # 서식: 문단별 정렬과 글자 크기를 글자 수로 가중해 본다(2026-10-09). 기준은 글자 16·왼쪽 정렬이다.
    size, centered, total = Counter(), 0, 0
    for cls, inner in re.findall(r'<p class="(se-text-paragraph[^"]*)"[^>]*>(.*?)</p>', body, flags=re.S):
        n = len(re.sub(r"<[^>]+>", "", inner).replace("​", "").strip())
        total += n
        centered += n if "se-text-paragraph-align-center" in cls else 0
        for fs, seg in re.findall(r'<span[^>]*class="[^"]*se-fs-fs(\d+)[^"]*"[^>]*>(.*?)</span>', inner, flags=re.S):
            size[fs] += len(re.sub(r"<[^>]+>", "", seg))

    return {
        "font": size.most_common(1)[0][0] if size else "",
        "center_pct": round(100 * centered / total) if total else 0,
        "tables": len(re.findall(r'se-component se-table[ "]', body)),
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


def selftest():
    """네이버가 내려주는 형태 그대로 넣어 파싱이 맞는지 본다.

    gsTagName 대신 baLogData의 tagNames를 읽어 "태그 없음"으로 오판한 적이 있다.
    필드 이름이 바뀌면 여기서 먼저 깨져야 한다.
    """
    html = (
        '<meta name="robots" content="index,follow"/>'
        '<div class="se-main-container">'
        '<div class="se-component se-image se-l-default"><img src="x.png"></div>'
        '<div class="se-component se-quotation se-l-quotation_line">소제목 하나</div>'
        '<div class="se-component se-text">'
        '<p class="se-text-paragraph se-text-paragraph-align-center "><span class="se-fs-fs13 se-ff-">사진 출처</span></p>'
        '<p class="se-text-paragraph se-text-paragraph-align- "><span class="se-fs-fs16 se-ff-">본문 문장입니다. 왼쪽으로 정렬된 열여섯 크기 글자입니다.</span></p>'
        '</div>'
        '<div class="se-component se-table se-l-default"><table><tr><td>표</td></tr></table></div>'
        '<div class="se-component se-quotation se-l-quotation_line">소제목 둘</div>'
        '<div class="se-component se-oglink"><a href="https://blog.naver.com/education_blog/224422755053">링크</a></div>'
        '</div></div>'
        '<script>jindo.m.patch("1.12.0"); var 본문이아닌스크립트 = "' + "가" * 5000 + '";'
        'var gsTagName = "근로장려금,홈택스,절세"; var x = 1;'
        '"tagNames":"",</script>'
    )
    r = parse(html)
    assert r["tags"] == ["근로장려금", "홈택스", "절세"], r["tags"]
    assert r["images"] == 1, r["images"]
    assert r["subheads"] == 2, r["subheads"]
    assert r["inlinks"] == 1, r["inlinks"]
    assert r["tistory"] == 0, r["tistory"]
    assert 10 < r["chars"] < 80, r["chars"]        # 본문 뒤 스크립트가 글자수에 섞이면 안 된다
    assert (r["font"], r["tables"]) == ("16", 1), (r["font"], r["tables"])
    assert 10 < r["center_pct"] < 20, r["center_pct"]      # 5자(출처) / 36자 — 글자 수로 가중한다
    try:
        parse("<html><body>본문 없음</body></html>")
        raise AssertionError("본문을 못 찾았는데 0자로 통과시켰다")
    except ValueError:
        pass

    assert expected_category("실업급여 조건 2026, 6개월 다녔는데") == "실업급여·고용보험"
    assert expected_category("2026 근로장려금 대상 기준") == "근로장려금·자녀장려금"
    assert title_shape("가, 나 하는 이유") == title_shape("다, 라 되는 이유")
    assert title_shape("가, 나 하는 이유") != title_shape("다, 라 되는 순서")
    print("selftest ok")


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
        print(f"  글자 크기 {r['font'] or '?'} / 가운데 정렬 {r['center_pct']}% / 표 {r['tables']}")

        if r["font"] and r["font"] != BODY_FONT:
            problems.append(f"{p['logNo']} 본문 글자 크기가 {r['font']} (기준 {BODY_FONT})")
        if r["center_pct"] > MAX_CENTER_PCT:
            problems.append(f"{p['logNo']} 가운데 정렬이 {r['center_pct']}% (사진 출처 줄만, {MAX_CENTER_PCT}% 이하)")

        if not r["tags"]:
            problems.append(f"{p['logNo']} 태그가 비어 있다")
        if r["images"] < 2:
            problems.append(f"{p['logNo']} 이미지가 {r['images']}장 (최소 2장)")
        if not 800 <= r["chars"] <= 2800:    # 원고 기준(12편부터 1,500~2,500자)에 경험 문장·출처 줄이 더 붙는다
            problems.append(f"{p['logNo']} 분량 {r['chars']}자 (800~2800)")
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
    if "--selftest" in sys.argv:
        selftest()
    else:
        sys.exit(main(sys.argv[1:]))
