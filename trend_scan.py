"""안 쓴 주제의 검색 추세 스캔 — 네이버 DataLab(검색어트렌드)으로 급상승/안정/하락을 가른다.

    python -X utf8 trend_scan.py             # 상위 30개 스캔 → _workspace/reports/trend_YYYY-MM-DD.md
    python -X utf8 trend_scan.py --top 50
    python -X utf8 trend_scan.py --selftest

.env에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 필요 — 2026-07-31 이전에 네이버 개발자센터에서 받은 키만 동작한다
(2027-06-30까지). 그 뒤로 개발자센터는 데이터랩 신규 신청을 받지 않고, 신규 키는 NAVER API HUB(NCP 계정)에서
받아야 하는데 호스트·경로·헤더가 달라 이 스크립트는 아직 대응하지 않는다. 2026-10-05에 '개발자센터에서
발급하라'는 안내를 따라갔다가 사용 API 목록에 데이터랩이 없어서 알았다. 키가 없으면 추세 없이 진행한다.
후보는 keyword_research.gap_data()의 '수요 있는데 안 쓴 주제' 중 NAVER_GUIDE 범위 안의 것만 쓴다.

sns_harness의 NaverDataLabClient를 import하지 않는 이유: 그 모듈이 sns_harness.models를 끌어오고
models가 regex·pydantic을 요구해서 루트 환경에서 import가 깨진다. 호출 자체는 requests POST 한 번이다.
"""
import datetime
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from keyword_research import gap_data

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

ENDPOINT = "https://openapi.naver.com/v1/datalab/search"
WINDOW_DAYS = 84        # 최근 4주 + 직전 8주
RECENT = 28
RISING, FALLING = 1.3, 0.7
COMP_W = {"낮음": 1.0, "중간": 0.6, "높음": 0.25}
TREND_W = {"급상승": 1.3, "안정": 1.0, "하락": 0.6, "데이터없음": 0.5}

# NAVER_GUIDE.md '주제 범위'. 가져갈 것 / 버릴 것을 코드로도 고정한다.
SCOPE = ["근로장려금", "자녀장려금", "실업급여", "구직급여", "고용보험", "국민연금", "노령연금",
         "기초연금", "건강보험", "연말정산", "재산세", "자동차세", "종합소득세", "부가세", "정부지원"]
EXCLUDE = ["대출", "금리", "보험비교", "견적", "ETF", "주식", "주가", "코인",
           # 사이트를 찾아가려는 검색(길찾기)은 글로 충족되지 않는다
           "공단", "EDI", "홈페이지", "고객센터", "지사", "포털", "로그인", "사이트"]


def in_scope(kw):
    flat = kw.replace(" ", "")
    return any(s in flat for s in SCOPE) and not any(x in flat for x in EXCLUDE)


def classify(values):
    """일별 ratio 목록 → (최근4주 평균 / 직전 평균, 방향). 직전이 0이면 비율은 None."""
    recent, prior = values[-RECENT:], values[:-RECENT]
    r = sum(recent) / len(recent) if recent else 0.0
    p = sum(prior) / len(prior) if prior else 0.0
    if r == 0 and p == 0:
        return None, "데이터없음"
    if p == 0:
        return None, "급상승"
    g = r / p
    return g, "급상승" if g >= RISING else "하락" if g <= FALLING else "안정"


def score(volume, comp, direction):
    """월 검색량 × 경쟁 가중 × 추세 가중. 시즌·카테고리 균형은 topic-planner 스킬이 판단한다."""
    return volume * COMP_W.get(comp, 0.25) * TREND_W[direction]


def build_batches(cands, anchor):
    """DataLab은 요청당 5그룹이고 요청마다 최댓값이 100이 된다. 앵커를 매 요청에 넣어 요청 간 비교가 되게 한다."""
    rest = [c for c in cands if c != anchor]
    return [[anchor] + rest[i:i + 4] for i in range(0, len(rest), 4)]


def anchor_levels(batch_results, anchor, ref):
    """batch_results: [{키워드: 평균ratio}, ...]. 앵커 평균이 ref가 되도록 각 요청을 재조정한 키워드별 수준."""
    out = {}
    for res in batch_results:
        a = res.get(anchor, 0.0)
        if a == 0:
            continue
        for kw, v in res.items():
            if kw != anchor:
                out[kw] = v / a * ref
    return out


def fetch(batch, start, end, cid, secret):
    payload = {"startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "date",
               "keywordGroups": [{"groupName": k, "keywords": [k]} for k in batch]}
    r = requests.post(ENDPOINT, json=payload, timeout=20,
                      headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret})
    r.raise_for_status()
    return {item["title"]: [float(p.get("ratio", 0)) for p in item.get("data", [])]
            for item in r.json().get("results", [])}


def scan(top):
    cid, secret = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
    if not (cid and secret):
        sys.exit("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 .env에 없습니다. 개발자센터 신규 발급은 2026-07-31에 "
                 "종료됐고, NAVER API HUB 키는 이 스크립트가 아직 지원하지 않습니다. 추세 없이 진행하세요.")
    gaps, _, age = gap_data()
    meta = {k: (v, c) for k, v, c in gaps if in_scope(k)}
    cands = list(meta)[:top]
    if len(cands) < 5:
        sys.exit(f"범위 안 후보가 {len(cands)}개뿐입니다. keywords_volume.csv 또는 SCOPE를 확인하세요.")
    anchor = sorted(cands, key=lambda k: meta[k][0])[len(cands) // 2]

    end = datetime.date.today() - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=WINDOW_DAYS - 1)
    series, means = {}, []
    for batch in build_batches(cands, anchor):
        got = fetch(batch, start, end, cid, secret)
        means.append({k: sum(v) / len(v) for k, v in got.items() if v})
        series.update({k: v for k, v in got.items() if k != anchor or k not in series})
    ref = next((m[anchor] for m in means if m.get(anchor)), 0.0)
    levels = anchor_levels(means, anchor, ref)
    levels[anchor] = ref

    rows = []
    for k in cands:
        g, d = classify(series.get(k, []))
        rows.append((k, meta[k][0], meta[k][1], g, d, levels.get(k, 0.0), score(meta[k][0], meta[k][1], d)))
    rows.sort(key=lambda r: -r[6])

    out = [f"# 추세 스캔 {end.isoformat()} (최근 {RECENT}일 vs 직전 {WINDOW_DAYS - RECENT}일)",
           f"- 후보 {len(cands)}개, 앵커 `{anchor}` / 검색량 데이터 {age}일 경과", "",
           "| 키워드 | 월 검색량 | 경쟁 | 추세 비율 | 방향 | 상대 수준 | 점수 |", "|---|---|---|---|---|---|---|"]
    for k, v, c, g, d, lv, sc in rows:
        out.append(f"| {k} | {v:,} | {c} | {'신규' if g is None and d == '급상승' else '-' if g is None else f'{g:.2f}'} "
                   f"| {d} | {lv:.1f} | {sc:,.0f} |")
    out += ["", "- 연말정산·근로장려금 등은 계절 상승이 섞여 있다. '급상승'은 올해 수요 확인용이지 신규 이슈 확정이 아니다."]
    path = ROOT / "_workspace" / "reports" / f"trend_{end.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"\n저장: {path}")


def selftest():
    flat = [10.0] * 84
    assert classify(flat) == (1.0, "안정")
    assert classify([10.0] * 56 + [25.0] * 28)[1] == "급상승"
    assert classify([10.0] * 56 + [4.0] * 28)[1] == "하락"
    assert classify([0.0] * 84) == (None, "데이터없음")
    assert classify([0.0] * 56 + [5.0] * 28) == (None, "급상승"), "직전 0인 신규 상승을 못 잡음"

    assert in_scope("국민연금수령나이") and in_scope("건강보험료 계산")
    assert not in_scope("삼성전자주가") and not in_scope("근로장려금대출"), "범위 필터 오동작"
    assert not in_scope("국민연금공단") and not in_scope("국민연금EDI"), "길찾기 검색어가 후보에 남음"

    cands = [f"k{i}" for i in range(11)]
    batches = build_batches(cands, "k5")
    assert all(len(b) <= 5 and b[0] == "k5" for b in batches), "배치 크기·앵커 위치 위반"
    assert sorted(x for b in batches for x in b[1:]) == sorted(c for c in cands if c != "k5"), "후보 누락/중복"

    assert score(1000, "낮음", "급상승") > score(1000, "높음", "급상승"), "경쟁 가중 방향 반대"
    assert score(1000, "중간", "급상승") > score(1000, "중간", "하락"), "추세 가중 방향 반대"

    # 요청1에서 앵커가 100, 요청2에서 앵커가 50이면 요청2의 키워드는 2배로 환산돼야 한다
    lv = anchor_levels([{"a": 100.0, "x": 10.0}, {"a": 50.0, "y": 10.0}], "a", 100.0)
    assert lv == {"x": 10.0, "y": 20.0}, lv
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        scan(int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 30)
