"""키워드 수요 조사 — 후보 발굴(키 불필요) + 실제 검색량 조회(네이버 검색광고 API).

사용법:
    python -X utf8 keyword_research.py expand          # 자동완성으로 후보 수집 → _workspace/keywords_candidates.json
    python -X utf8 keyword_research.py volume          # 후보의 월 검색량 조회 → _workspace/keywords_volume.csv

volume 모드는 .env에 아래 3개가 있어야 한다(네이버 검색광고 > 도구 > API 사용관리에서 무료 발급):
    NAVER_AD_API_KEY / NAVER_AD_SECRET_KEY / NAVER_AD_CUSTOMER_ID
"""
import sys, json, time, hmac, hashlib, base64, csv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import requests
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / ".env")
WS = Path(__file__).parent / "_workspace"
UA = {"User-Agent": "Mozilla/5.0"}

# 블로그의 기존 카테고리에서 뽑은 시드. 카테고리별로 고르게 배치한다.
SEEDS = [
    # 절세·연금
    "연말정산", "근로장려금", "자녀장려금", "종합소득세", "국민연금", "기초연금",
    "퇴직금", "퇴직연금", "연금저축", "IRP", "ISA 계좌", "상속세", "증여세",
    "재산세", "자동차세", "부가가치세 신고", "월세 세액공제", "건강보험료",
    # 대출·금리
    "전세대출", "주택담보대출", "신용대출", "대출 금리", "중도상환수수료",
    "버팀목 전세자금대출", "DSR", "전세보증보험", "햇살론",
    # 보험
    "실손보험", "자동차보험", "암보험", "운전자보험", "보험 해지환급금",
    # 카드
    "신용카드 추천", "체크카드", "카드 포인트", "전월실적", "리볼빙",
    # 예금·투자
    "예금 금리", "파킹통장", "적금 추천", "ETF 추천", "배당주", "주식 세금",
    # 정부지원
    "실업급여", "청년 지원금", "기초생활수급자", "국민취업지원제도",
]
SUFFIXES = ["", " 조건", " 신청", " 계산", " 얼마", " 방법", " 기간", " 대상", " 후기", " 비교"]


def _naver_ac(q):
    try:
        r = requests.get("https://ac.search.naver.com/nx/ac",
                         params={"q": q, "st": "100", "r_format": "json",
                                 "r_enc": "UTF-8", "q_enc": "UTF-8", "frm": "nv"},
                         timeout=10, headers=UA)
        return [i[0] for i in r.json()["items"][0]]
    except Exception:
        return []


def _google_ac(q):
    try:
        r = requests.get("https://suggestqueries.google.com/complete/search",
                         params={"client": "firefox", "hl": "ko", "gl": "kr", "q": q},
                         timeout=10, headers=UA)
        return json.loads(r.text)[1]
    except Exception:
        return []


def expand():
    """시드 × 접미사를 두 엔진 자동완성에 던져 후보를 모은다.

    자동완성은 실제 검색 로그에서 나오므로 '아무도 안 치는 말'을 걸러준다.
    다만 검색량 자체는 알 수 없어, 등장 빈도를 인기 대리지표로만 쓴다.
    """
    queries = [s + suf for s in SEEDS for suf in SUFFIXES]
    hits = {}

    def work(q):
        out = []
        for engine, fn in (("naver", _naver_ac), ("google", _google_ac)):
            for rank, kw in enumerate(fn(q)):
                out.append((kw.strip(), engine, rank))
        time.sleep(0.05)
        return out

    with ThreadPoolExecutor(6) as ex:
        for res in ex.map(work, queries):
            for kw, engine, rank in res:
                d = hits.setdefault(kw, {"kw": kw, "n": 0, "engines": set(), "best_rank": 99})
                d["n"] += 1
                d["engines"].add(engine)
                d["best_rank"] = min(d["best_rank"], rank)

    rows = []
    for d in hits.values():
        if len(d["kw"]) < 4 or len(d["kw"]) > 40:
            continue
        rows.append({"kw": d["kw"], "freq": d["n"], "engines": sorted(d["engines"]),
                     "both": len(d["engines"]) == 2, "best_rank": d["best_rank"]})
    rows.sort(key=lambda r: (-r["both"], -r["freq"], r["best_rank"]))
    WS.mkdir(exist_ok=True)
    (WS / "keywords_candidates.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"질의 {len(queries)}개 → 후보 {len(rows)}개 저장: _workspace/keywords_candidates.json")
    print(f"  양쪽 엔진 모두 제안: {sum(1 for r in rows if r['both'])}개")
    for r in rows[:25]:
        print(f"   {r['kw'][:32]:<32} freq {r['freq']:>2} {'both' if r['both'] else r['engines'][0]}")


def _signature(ts, method, path, secret):
    msg = f"{ts}.{method}.{path}"
    return base64.b64encode(hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()


def volume(chunk_limit=5):
    """네이버 검색광고 keywordstool로 월간 검색수(PC/모바일)를 받아온다."""
    key, secret, cid = (os.getenv("NAVER_AD_API_KEY"), os.getenv("NAVER_AD_SECRET_KEY"),
                        os.getenv("NAVER_AD_CUSTOMER_ID"))
    if not all([key, secret, cid]):
        sys.exit("NAVER_AD_API_KEY / NAVER_AD_SECRET_KEY / NAVER_AD_CUSTOMER_ID 가 .env에 필요합니다.")

    cands = json.loads((WS / "keywords_candidates.json").read_text(encoding="utf-8"))
    kws = [c["kw"] for c in cands]
    path, out = "/keywordstool", []

    for i in range(0, len(kws), chunk_limit):
        batch = [k.replace(" ", "") for k in kws[i:i + chunk_limit]]
        ts = str(round(time.time() * 1000))
        headers = {"X-Timestamp": ts, "X-API-KEY": key, "X-Customer": str(cid),
                   "X-Signature": _signature(ts, "GET", path, secret)}
        try:
            r = requests.get("https://api.searchad.naver.com" + path, headers=headers,
                             params={"hintKeywords": ",".join(batch), "showDetail": "1"}, timeout=15)
            if r.status_code != 200:
                print("  실패", r.status_code, r.text[:120]); time.sleep(1); continue
            for row in r.json().get("keywordList", []):
                pc = row.get("monthlyPcQcCnt", 0)
                mo = row.get("monthlyMobileQcCnt", 0)
                to_i = lambda v: int(str(v).replace("<", "").replace(",", "").strip() or 0)
                out.append({"keyword": row.get("relKeyword"), "pc": to_i(pc), "mobile": to_i(mo),
                            "total": to_i(pc) + to_i(mo), "comp": row.get("compIdx", "")})
        except Exception as e:
            print("  오류", repr(e)[:80])
        time.sleep(0.35)  # ponytail: 고정 대기. 429가 잦아지면 지수 백오프로 교체

    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: -r["total"]):
        if r["keyword"] in seen:
            continue
        seen.add(r["keyword"]); uniq.append(r)
    p = WS / "keywords_volume.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["keyword", "pc", "mobile", "total", "comp"])
        w.writeheader(); w.writerows(uniq)
    print(f"검색량 {len(uniq)}개 저장: {p}")
    for r in uniq[:30]:
        print(f"   {r['keyword'][:30]:<30} 월 {r['total']:>7,} (모바일 {r['mobile']:>6,}) 경쟁 {r['comp']}")


STALE_DAYS = 30
NAVER_DIR = Path(__file__).parent / "content" / "naver"


def _norm(s):
    import unicodedata
    return unicodedata.normalize("NFC", s).replace(" ", "")


def is_covered(kw, titles):
    toks = [t for t in kw.split() if len(t) > 1] or [kw]
    flat = _norm(kw)
    return any(flat in t or all(_norm(tok) in t for tok in toks) for t in titles)


def naver_titles(directory=NAVER_DIR):
    """content/naver/NN_*.md 첫 줄 '제목: ...'. 태그는 넓어서(#근로장려금 등) 오탐이 커 제목만 쓴다."""
    out = []
    for p in sorted(Path(directory).glob("[0-9][0-9]_*.md")):
        first = p.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("제목:"), f"{p.name}: 첫 줄이 '제목:'이 아님"
        out.append(first[3:].strip())
    return out


def volume_age_days(path):
    import datetime
    return (datetime.datetime.now() - datetime.datetime.fromtimestamp(path.stat().st_mtime)).days


def gap_data(min_vol=1000):
    """검색량 표를 티스토리 라이브 글과 네이버 원고 제목에 대조해 (기회, 이미 다룸, 데이터 경과일)을 돌려준다.

    형태소 분석 없이 토큰 포함 여부로만 매칭한다 —
    ponytail: 단순 포함 매칭. 오탐이 늘면 그때 형태소 분석기 도입.
    """
    vol_path = WS / "keywords_volume.csv"
    rows = list(csv.DictReader(open(vol_path, encoding="utf-8-sig")))
    live = json.loads((WS / "live_posts.json").read_text(encoding="utf-8"))
    titles = [_norm(p["title"]) for p in live] + [_norm(t) for t in naver_titles()]

    hits, gaps = [], []
    for r in rows:
        v = int(r["total"])
        if v < min_vol:
            continue
        (hits if is_covered(r["keyword"], titles) else gaps).append((r["keyword"], v, r["comp"]))
    return gaps, hits, volume_age_days(vol_path)


def gap(min_vol=1000, as_json=False):
    gaps, hits, age = gap_data(min_vol)
    if as_json:
        print(json.dumps({"volume_age_days": age, "min_vol": min_vol,
                          "gaps": [dict(keyword=k, total=v, comp=c) for k, v, c in gaps],
                          "covered": [dict(keyword=k, total=v, comp=c) for k, v, c in hits]},
                         ensure_ascii=False))
        return
    if age > STALE_DAYS:
        print(f"⚠ keywords_volume.csv가 {age}일 전 데이터입니다 (기준 {STALE_DAYS}일). "
              "keyword_research.py volume 재실행 권장\n")
    print(f"검색량 {min_vol}+ 키워드 {len(hits) + len(gaps)}개 | 이미 다룸 {len(hits)} | 미작성 {len(gaps)}\n")
    print("=== 수요 있는데 안 쓴 주제 TOP 40 ===")
    for k, v, c in gaps[:40]:
        print(f"   {k[:34]:<34} 월 {v:>7,}  경쟁 {c}")
    print("\n=== 이미 쓴 주제 중 검색량 큰 것 TOP 20 (재작성 후보) ===")
    for k, v, c in hits[:20]:
        print(f"   {k[:34]:<34} 월 {v:>7,}  경쟁 {c}")


def _demo():
    import tempfile
    assert _signature("1", "GET", "/x", "s"), "서명 생성 실패"
    assert len(SEEDS) == len(set(SEEDS)), "시드 중복"
    titles = [_norm("국민연금수령나이 총정리, 조기수령과 연기수령 감액표")]
    assert is_covered("국민연금수령나이", titles), "붙여쓴 키워드 매칭 실패"
    assert is_covered("국민연금 수령나이", titles), "띄어쓴 키워드 매칭 실패"
    assert not is_covered("실업급여", titles), "무관한 키워드가 다룸으로 잡힘"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "01_x.md").write_text("제목: 테스트 제목\n\n본문", encoding="utf-8")
        (Path(d) / "_calendar.md").write_text("제목 없음", encoding="utf-8")
        assert naver_titles(d) == ["테스트 제목"], "네이버 원고 제목 추출 실패"
    assert len(naver_titles()) >= 1, "content/naver 원고 제목을 하나도 못 읽음"
    print("demo ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "expand"
    if cmd == "gap":
        gap(as_json="--json" in sys.argv[2:])
    else:
        {"expand": expand, "volume": volume, "demo": _demo, "selftest": _demo}[cmd]()
