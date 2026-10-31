"""제목 게이트 — 후보를 차단·감점하고 85점 이상 최대 3개를 남긴다 (30편~). 명세 V2 7·8절.

    python -X utf8 title_gate.py NN           # content/naver/_titles/NN.json을 판정해 결과를 같은 파일에 쓴다
    python -X utf8 title_gate.py --serp 검색어  # 블로그 탭 상위 10개 제목 (serp_titles 칸에 넣는다)
    python -X utf8 title_gate.py --selftest

후보는 Claude가 쓴다. intent·clarity·specificity·differentiation 네 점수는 Claude의 자기 채점이고(이유 필수),
코드는 키워드·최신성·모바일 점수와 차단·감점만 객관적으로 판정한다. 점수는 근거 기록이지 품질 보증이 아니다.
"""
import datetime
import json
import re
import sys
from pathlib import Path

from check_naver import facts, memo_value, parts, unit_nums
from pipeline import contain, DIR, existing_titles, jaccard

TITLES = DIR / "_titles"
INPUT_KEYS = ("primary_query", "primary_intent", "reader_problem", "verified_facts", "unique_value",
              "serp_repeated_terms", "serp_gaps", "serp_titles", "publication_date")
SELF_SCORED = {"intent": 25, "clarity": 15, "specificity": 15, "differentiation": 10}
FINAL_AT, REWORK_AT, MAX_FINAL, MIN_CANDIDATES = 85, 75, 3, 8
OVERLAP_BLOCK, OVERLAP_WARN = 0.70, 0.50
SERP_SIMILAR = 0.60

STALE_RE = re.compile(r"열리기 전|개통 전|오픈 전|오픈 예정|곧 (?:열|개통|오픈)|작년 \d+월")
BANNED_RE = re.compile(r"무조건|폭탄|안 보면 손해|황금 공식|끝판왕")
BENEFIT_RE = re.compile(r"\d+\s?만원 더|더 받는|더 돌려받")
FILLER_RE = re.compile(r"총정리|완벽정리")
MISLEADING_RE = re.compile(r"카드 합산")         # 합산이 되는 것처럼 읽힌다(27편 원고 제목)
DIRECTION_RE = re.compile(r"과다|누락|더 받|덜 받")


def strip_query(title: str, query: str) -> str:
    """검색어 필수 표현은 유사도에서 뺀다."""
    for w in sorted(query.split(), key=len, reverse=True):
        title = title.replace(w, " ")
    return re.sub(r"[\s|｜:]+", "", re.sub(r"20\d\d", "", title))


def fact_units(md: str) -> tuple:
    rows = [r for r in facts(md) if r[4] in ("VERIFIED", "계산")]
    return (set().union(*(unit_nums(r[1]) for r in rows)) if rows else set(),
            set().union(*(unit_nums(r[1]) for r in rows if r[4] == "계산")) if rows else set(),
            any("개통" in r[0] + r[1] for r in rows))


def judge(cand: dict, query: str, md: str, existing: dict, serp_titles: list) -> dict:
    """후보 하나 → {title, score, status, reasons}. status: FINAL·REWORK·DISCARD 또는 BLOCKED_/REJECT_ 코드."""
    title = cand["title"].strip()
    known, calc, opened = fact_units(md)
    _, body, text, _ = parts_md(md)
    reasons = []

    def out(status):
        return {"title": title, "score": 0, "status": status, "reasons": reasons}

    if STALE_RE.search(title) and opened:
        reasons.append("이미 개통된 서비스를 지난 상태로 썼다")
        return out("BLOCKED_STALE_TITLE")
    if m := BANNED_RE.search(title):
        reasons.append(f"금지 표현: {m.group(0)}")
        return out("REJECT_BANNED")
    if BENEFIT_RE.search(title) and not (unit_nums(title) and unit_nums(title) <= calc):
        reasons.append("제목의 혜택을 계산 행으로 재현할 수 없다")
        return out("REJECT_UNSUPPORTED_BENEFIT_CLAIM")
    missing = unit_nums(title) - known
    if missing:
        reasons.append("수치 근거 표에 없는 숫자: " + ", ".join(a + b for a, b in sorted(missing)))
        return out("REJECT_UNVERIFIED")
    best, cover = max(((k, contain(title_core(title), v)) for k, v in existing.items()), key=lambda x: x[1], default=("", 0))
    if cover >= OVERLAP_BLOCK:
        reasons.append(f"{best}편과 검색 의도 {cover:.0%} 겹침 — 새 글 대신 기존 글 보강")
        return out("REJECT_CANNIBALIZE")

    words = query.split()
    hit = sum(w in title for w in words) / max(len(words), 1)
    front = title[:30]
    keyword = round(15 * hit) - (5 if words and words[0] not in front else 0)
    mobile = 5 if len(title) <= 40 else 3 if len(title) <= 50 else 1
    if len(re.findall(r"\d+(?:[.,]\d+)*", re.sub(r"20\d\d", "", title))) > 2:
        mobile = max(0, mobile - 2)
        reasons.append("숫자가 핵심 기준 2개를 넘는다")
    score = keyword + 15 + mobile + sum(min(int(cand[k]), hi) for k, hi in SELF_SCORED.items())

    hype = 0
    if FILLER_RE.search(title):
        hype += 10
        reasons.append("차별점 없는 총정리류")
    if MISLEADING_RE.search(title):
        hype += 10
        reasons.append("`카드 합산`은 합산이 되는 것처럼 읽힌다")

    mismatch = 0
    if re.search(r"누구|유리", title) and not re.search(r"(?m)^\|.*\n\|[-: |]+\|\n\|.*\n\|", body):
        mismatch += 20
        reasons.append("`누구·유리`를 약속했는데 비교 2건 이상의 표가 없다")
    if re.search(r"조회\s?방법|경로", title) and not memo_value(md, "화면 확인"):
        mismatch += 20
        reasons.append("조회 방법을 약속했는데 `- 화면 확인:`이 없다")
    if "수정신고" in title and "경정청구" in title:
        if not ("수정신고" in text and "경정청구" in text):
            mismatch += 20
            reasons.append("두 절차를 약속했는데 본문에 둘 다 있지 않다")
        if not DIRECTION_RE.search(title):
            mismatch += 15
            reasons.append("반대 방향의 두 절차를 방향 없이 나열했다")

    overlap = round(30 * (cover - OVERLAP_WARN) / (OVERLAP_BLOCK - OVERLAP_WARN)) if cover > OVERLAP_WARN else 0
    if overlap:
        reasons.append(f"{best}편과 {cover:.0%} 겹침")
    core = strip_query(title, query)
    similar = max((jaccard(core, strip_query(t, query)) for t in serp_titles), default=0)
    if similar >= SERP_SIMILAR:
        hype += 10
        reasons.append(f"상위 제목과 {similar:.0%} 비슷하다")
    score -= min(hype, 30) + min(overlap, 30) + min(mismatch, 40)
    return {"title": title, "score": score,
            "status": "FINAL" if score >= FINAL_AT else "REWORK" if score >= REWORK_AT else "DISCARD", "reasons": reasons}


def title_core(title: str) -> str:
    return re.sub(r"20\d\d", "", re.sub(r"[|｜:]", " ", title)).strip()


def parts_md(md: str) -> tuple:
    """check_naver.parts는 파일 경로를 받는다 — 문자열로 판정하려고 임시 파일을 거친다."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.md")
        Path(path).write_text(md, encoding="utf-8")
        return parts(path)


def decide(data: dict, md: str, existing: dict) -> dict:
    """입력 계약 + 후보 → 판정 결과가 붙은 data. 계약이 비면 ValueError."""
    empty = [k for k in INPUT_KEYS if not data.get(k)]
    if empty:
        raise ValueError(f"입력 계약이 비었다: {', '.join(empty)} — 제목부터 만들지 않는다")
    cands = data.get("candidates", [])
    if len(cands) < MIN_CANDIDATES:
        raise ValueError(f"후보 {len(cands)}개 ({MIN_CANDIDATES}~12개)")
    for c in cands:
        lack = [k for k in (*SELF_SCORED, "title", "why") if not str(c.get(k, "")).strip()]
        if lack:
            raise ValueError(f"후보에 없는 칸 {lack}: {c.get('title', '')[:24]}")
    results = sorted((judge(c, data["primary_query"], md, existing, data["serp_titles"]) for c in cands),
                     key=lambda r: -r["score"])
    final = [r for r in results if r["status"] == "FINAL"][:MAX_FINAL]
    data.update(results=results, selected_title=final[0]["title"] if final else "",
                score=final[0]["score"] if final else 0,
                alternatives=[{"title": r["title"], "score": r["score"]} for r in final[1:]],
                rejected=[{"title": r["title"], "reason": r["status"], "detail": r["reasons"]}
                          for r in results if r["status"] not in ("FINAL", "REWORK")],
                verified_at=datetime.datetime.now().isoformat(timespec="minutes"))
    return data


def serp_titles(query: str) -> list:
    import html
    import requests
    from keyword_research import serp, SERP_TOP, UA
    out = []
    for blog, no in serp(query)[:SERP_TOP]:
        r = requests.get(f"https://m.blog.naver.com/{blog}/{no}", headers=UA, timeout=15)
        m = re.search(r'property="og:title" content="([^"]+)"', r.text)
        if not m:       # 못 읽은 것을 빈 값으로 넘기면 유사도가 0으로 통과한다
            raise RuntimeError(f"{blog}/{no} 제목을 못 읽었다 — 마크업 변경 또는 차단")
        out.append(html.unescape(m.group(1)))
    return out


def run(nn: int) -> int:
    path = TITLES / f"{nn:02d}.json"
    src = next(DIR.glob(f"{nn:02d}_*.md"), None)
    if not path.exists() or not src:
        print(f"{path.name} 또는 {nn:02d}편 원고가 없다")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = {k: v for k, v in existing_titles().items() if int(k) != nn}
    try:
        decide(data, src.read_text(encoding="utf-8"), existing)
    except ValueError as e:
        print("BLOCKED_NEEDS_REVIEW —", e)
        return 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in data["results"]:
        print(f"{r['score']:>3} {r['status']:<32} {r['title']}" + (f"  ({'; '.join(r['reasons'])})" if r["reasons"] else ""))
    print("\n선정:", data["selected_title"] or "없음 — 85점 이상 후보가 없다. 후보를 고친다")
    return 0 if data["selected_title"] else 1


def selftest():
    fact_tbl = ("### 수치 근거\n\n| 항목 | 값 | 출처·식 | 확인일 | 상태 |\n|---|---|---|---|---|\n"
                "| 올해 개통 | 10월 28일 | 국세청 | 2026-10-31 | VERIFIED |\n"
                "| 카드 문턱 | 25% | 국세청 | 2026-10-31 | VERIFIED |\n"
                "| 경정청구 기한 | 5년 | 국세기본법 | 2026-10-31 | VERIFIED |\n")
    body = ("제목: 임시\n\n본문입니다. 수정신고와 경정청구는 반대 방향입니다.\n\n| 사례 | 값 |\n|---|---|\n| 가 | 1 |\n| 나 | 2 |\n\n"
            "## 작성 메모\n\n" + fact_tbl)
    high = dict(intent=25, clarity=15, specificity=15, differentiation=10, why="근거")

    def j(title, query, md=body, existing=None, serp=()):
        return judge({**high, "title": title}, query, md, existing or {}, list(serp))

    # TEST-TITLE-001: 이미 개통된 서비스 (옛 29편 실제 제목)
    r = j("2026 연말정산 미리보기 열리기 전에 | 작년 11월 5일 개통, 남은 카드 얼마 쓸까?", "연말정산 미리보기")
    assert r["status"] == "BLOCKED_STALE_TITLE", r
    r = j("2026 연말정산 미리보기 10월 28일 오픈｜홈택스 남은 카드 계산", "연말정산 미리보기")
    assert r["status"] == "FINAL", r
    # TEST-TITLE-002: 기존 글과 겹치면 새 글 금지, 그 글을 고칠 때는 자기 자신을 뺀다
    t27 = "2026 맞벌이 연말정산｜부양가족 공제는 누가? 카드 25% 기준까지"
    t2 = "2026 맞벌이 연말정산 부양가족 공제 누가 카드 25% 기준"
    assert j(t2, "맞벌이 연말정산", existing={"27": t27})["status"] == "REJECT_CANNIBALIZE"
    assert j(t2, "맞벌이 연말정산")["status"] == "FINAL"
    # TEST-TITLE-003: 실제 28편 제목. 2년 근거가 없으면 탈락, 근거가 있어도 방향 없는 나열은 감점
    t28 = "2026 연말정산 부양가족 잘못 공제했을 때｜경정청구와 수정신고, 5년·2년 기한은?"
    assert j(t28, "연말정산 부양가족")["status"] == "REJECT_UNVERIFIED"
    with2 = body + "| 감면 끝 | 2년 | 국세기본법 | 2026-10-31 | VERIFIED |\n"
    r = j(t28, "연말정산 부양가족", with2)
    assert r["status"] != "FINAL" and any("방향" in x for x in r["reasons"]), r
    r = j("2026 연말정산 부양가족 과다공제｜수정신고·가산세, 경정청구와 차이", "연말정산 부양가족")
    assert r["status"] == "FINAL", r
    # TEST-TITLE-004: 근거 없는 혜택
    t4 = "맞벌이 부부 연말정산 황금 공식｜환급금 100만원 더 받는 법"
    assert j(t4, "맞벌이 연말정산")["status"] in ("REJECT_BANNED", "REJECT_UNSUPPORTED_BENEFIT_CLAIM")
    assert j("맞벌이 연말정산｜환급금 100만원 더 받는 법", "맞벌이 연말정산")["status"] == "REJECT_UNSUPPORTED_BENEFIT_CLAIM"
    # TEST-TITLE-005: 26편과 같은 의도
    r = j("부모님과 따로 살아도 연말정산 부양가족 공제될까", "연말정산 부양가족",
          existing={"26": "따로 사는 부모님 연말정산 부양가족 공제 같이 안 살아도 가능할까 따로 살아도 부모님 공제"})
    assert r["status"] == "REJECT_CANNIBALIZE", r

    # 감점·약속 검사
    assert any("합산" in x for x in j("맞벌이 연말정산 카드 합산 25% 기준", "맞벌이 연말정산")["reasons"])
    assert any("표가 없다" in x for x in j("맞벌이 연말정산 누구에게 유리할까", "맞벌이 연말정산", body.replace("| 나 | 2 |\n", "").replace("| 가 | 1 |\n", ""))["reasons"])
    assert any("화면 확인" in x for x in j("연말정산 미리보기 조회방법", "연말정산 미리보기")["reasons"])
    assert any("비슷" in x for x in j("2026 연말정산 미리보기 카드 계산 순서", "연말정산 미리보기", serp=["연말정산 미리보기 카드 계산 순서 정리"])["reasons"])
    assert strip_query("2026 연말정산 미리보기｜순서", "연말정산 미리보기") == "순서"

    # 입력 계약 · 선정
    good = {k: "값" for k in INPUT_KEYS}
    good.update(primary_query="연말정산 미리보기", serp_titles=["다른 글 제목입니다"],
                candidates=[{**high, "title": f"2026 연말정산 미리보기 25% 카드 계산 {'가나다라마바사아'[i]}"} for i in range(8)])
    d = decide(dict(good), body, {})
    assert d["selected_title"] and len(d["alternatives"]) == MAX_FINAL - 1 and d["score"] >= FINAL_AT, d
    for broken in ({**good, "reader_problem": ""}, {**good, "candidates": good["candidates"][:3]},
                   {**good, "candidates": [{"title": "이유 없음", **{k: 1 for k in SELF_SCORED}}] * 8}):
        try:
            decide(dict(broken), body, {})
            raise AssertionError("빈 입력이 통과했다")
        except ValueError:
            pass
    low = {**good, "candidates": [{**high, "intent": 5, "clarity": 5, "title": f"2026 연말정산 미리보기 카드 {i}번"} for i in range(8)]}
    assert decide(dict(low), body, {})["selected_title"] == ""
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--serp" in sys.argv:
        print(json.dumps(serp_titles(" ".join(sys.argv[sys.argv.index("--serp") + 1:])), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1:
        sys.exit(run(int(sys.argv[1])))
    else:
        print(__doc__)
