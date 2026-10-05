"""블로그 매니저 — 현재 상태를 모으고, 미리 정해둔 기준으로 판정한다.

판정을 사람이나 에이전트가 아니라 이 파일의 상수가 내린다. 수치가 나쁠 때
"조금만 더"로 밀리지 않게 하려는 것이다. 기준을 바꾸려면 ADSENSE_PROGRESS.md에
날짜·사유를 남기고 selftest를 같이 고친다(.claude/CLAUDE.md 「블로그 매니저」).

    python -X utf8 manager.py                # 수집 + 판정
    python -X utf8 manager.py --visitors 37  # 어제 하루 방문자 수를 직접 기록
    python -X utf8 manager.py --selftest
"""
import csv
import datetime
import re
import sys
from pathlib import Path

import requests

import verify_naver
from keyword_research import STALE_DAYS, volume_age_days

ROOT = Path(__file__).parent
METRICS = ROOT / "content" / "naver" / "_metrics.csv"

# 판정 기준 (2026-10-05 확정). 편수·주차 중 먼저 오는 쪽에서 점검한다.
MID_POSTS, MID_WEEKS, MID_VISITORS = 10, 4, 15        # 미달 → 경고
FINAL_POSTS, FINAL_WEEKS, FINAL_VISITORS = 20, 8, 50  # 미달 → 전환권고
METRICS_MAX_AGE = 7   # 방문자 수치가 이보다 오래되면 판정하지 않는다
GSC_STALE_DAYS = 60


def judge(posts, weeks, avg7, metrics_age):
    """→ (판정, 근거). avg7·metrics_age는 수치가 없으면 None."""
    if posts >= FINAL_POSTS or weeks >= FINAL_WEEKS:
        stage, limit, fail = "최종 점검", FINAL_VISITORS, "전환권고"
    elif posts >= MID_POSTS or weeks >= MID_WEEKS:
        stage, limit, fail = "중간 점검", MID_VISITORS, "경고"
    else:
        return "관찰중", (f"점검 시점 전 ({posts}편·{weeks:.1f}주, "
                       f"중간 점검은 {MID_POSTS}편 또는 {MID_WEEKS}주)")
    if avg7 is None or metrics_age is None or metrics_age > METRICS_MAX_AGE:
        return "판정보류", f"{stage} 시점인데 최근 {METRICS_MAX_AGE}일 방문자 수치가 없다"
    if avg7 < limit:
        return fail, f"{stage}: 7일 평균 일 방문 {avg7:.1f}명 < 기준 {limit}명"
    return "OK", f"{stage}: 7일 평균 일 방문 {avg7:.1f}명 ≥ 기준 {limit}명"


def forecast(posts, weeks, avg7, metrics_age):
    """지금 수치가 그대로일 때 다음 점검에서 나올 판정. 최종 점검을 지났으면 None."""
    if posts >= FINAL_POSTS or weeks >= FINAL_WEEKS:
        return None
    at_mid = posts >= MID_POSTS or weeks >= MID_WEEKS
    return judge(FINAL_POSTS if at_mid else MID_POSTS, weeks, avg7, metrics_age)


def parse_visitors(xml: str) -> dict:
    return {datetime.datetime.strptime(d, "%Y%m%d").date(): int(c)
            for d, c in re.findall(r'<visitorcnt id="(\d{8})" cnt="(\d+)"', xml)}


def fetch_visitors() -> dict:
    # 방문자 그래프 위젯이 꺼져 있으면 204(빈 본문)가 온다.
    u = f"https://blog.naver.com/NVisitorgp4Ajax.nhn?blogId={verify_naver.BLOG}"
    return parse_visitors(verify_naver._get(u).text)


def load_metrics() -> dict:
    if not METRICS.exists():
        return {}
    with METRICS.open(encoding="utf-8", newline="") as f:
        return {datetime.date.fromisoformat(r["date"]): int(r["visitors"])
                for r in csv.DictReader(f)}


def save_metrics(rows: dict):
    with METRICS.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "visitors"])
        w.writerows((d.isoformat(), v) for d, v in sorted(rows.items()))


def avg7(rows: dict, today):
    """오늘은 집계 중이라 뺀다. → (최근 7일 평균, 마지막 수치 경과일)"""
    done = {d: v for d, v in rows.items() if d < today}
    if not done:
        return None, None
    week = [v for d, v in done.items() if (today - d).days <= 7]
    return (sum(week) / len(week) if week else None), (today - max(done)).days


def selftest():
    assert judge(8, 1.6, None, None)[0] == "관찰중"
    assert judge(10, 1.0, 14.9, 1)[0] == "경고"
    assert judge(9, 4.0, 15.0, 1)[0] == "OK"
    assert judge(19, 7.9, 20.0, 1)[0] == "OK"          # 아직 중간 기준 적용
    assert judge(20, 3.0, 49.9, 1)[0] == "전환권고"
    assert judge(12, 8.0, 49.9, 1)[0] == "전환권고"    # 편수가 적어도 8주면 최종
    assert judge(20, 8.0, 50.0, 1)[0] == "OK"
    assert judge(20, 8.0, 300.0, 8)[0] == "판정보류"   # 수치가 좋아도 오래됐으면 보류
    assert judge(20, 8.0, None, None)[0] == "판정보류"

    assert forecast(8, 1.3, 6.5, 1)[0] == "경고"         # 관찰중이어도 예고는 나온다
    assert forecast(8, 1.3, 15.0, 1)[0] == "OK"
    assert forecast(10, 2.0, 20.0, 1)[0] == "전환권고"   # 중간은 넘겼지만 최종엔 미달
    assert forecast(8, 1.3, None, None)[0] == "판정보류"
    assert forecast(20, 3.0, 49.9, 1) is None

    xml = ('<visitorcnts><visitorcnt id="20261003" cnt="12" />'
           '<visitorcnt id="20261004" cnt="30" /><visitorcnt id="20261005" cnt="4" /></visitorcnts>')
    rows = parse_visitors(xml)
    assert rows[datetime.date(2026, 10, 4)] == 30, rows
    assert parse_visitors("") == {}
    a, age = avg7(rows, datetime.date(2026, 10, 5))
    assert (a, age) == (21.0, 1), (a, age)             # 오늘(4명) 제외
    assert avg7(rows, datetime.date(2026, 10, 20)) == (None, 15)
    print("selftest ok")


def main(argv):
    today = datetime.date.today()
    rows = load_metrics()
    if "--visitors" in argv:
        rows[today - datetime.timedelta(days=1)] = int(argv[argv.index("--visitors") + 1])
    fetched = fetch_visitors()
    rows.update(fetched)
    if rows:
        save_metrics(rows)

    posts, page = [], 1
    while batch := verify_naver.recent(30, page):   # API 상한이 30개
        posts += batch
        page += 1
    dates = sorted(p["when"].date() for p in posts)
    weeks = (today - dates[0]).days / 7 if dates else 0.0
    a7, age = avg7(rows, today)
    verdict, why = judge(len(posts), weeks, a7, age)

    print(f"[판정] {verdict} — {why}")
    nxt = forecast(len(posts), weeks, a7, age)
    if nxt:
        print(f"[예상] 현재 수치가 유지되면 다음 점검에서 {nxt[0]} — {nxt[1]}")
    print(f"\n네이버 ({today})")
    print(f"  발행 {len(posts)}편 / 첫 발행 후 {weeks:.1f}주"
          + (f" / 마지막 발행 {(today - dates[-1]).days}일 전" if dates else ""))
    drafts = len({p.name[:2] for p in (ROOT / "content" / "naver").glob("[0-9][0-9]_*.md")})
    print(f"  원고 {drafts}편 → 미발행 {max(drafts - len(posts), 0)}편")
    if a7 is None:
        print("  방문자: 최근 7일 수치 없음"
              + ("" if fetched else " (위젯 엔드포인트 빈 응답 — 방문자 그래프 위젯을 켜거나 --visitors로 입력)"))
    else:
        print(f"  방문자: 7일 평균 {a7:.1f}명 (마지막 수치 {age}일 전)")
        for d, v in sorted(rows.items())[-7:]:
            print(f"    {d} {v}")

    print("\n데이터 신선도")
    vol = ROOT / "_workspace" / "keywords_volume.csv"
    if vol.exists():
        n = volume_age_days(vol)
        print(f"  검색량 {n}일 전" + (f"  ⚠ {STALE_DAYS}일 초과" if n > STALE_DAYS else ""))
    else:
        print("  검색량 파일 없음")
    gsc = sorted(re.findall(r"\d{4}-\d{2}-\d{2}", " ".join(p.name for p in (ROOT / "GSC").glob("*.zip"))))
    if gsc:
        n = (today - datetime.date.fromisoformat(gsc[-1])).days
        print(f"  GSC export {n}일 전 ({gsc[-1]})" + (f"  ⚠ {GSC_STALE_DAYS}일 초과" if n > GSC_STALE_DAYS else ""))
    cal = ROOT / "content" / "naver" / "_calendar.md"
    print("  글감 캘린더 " + ("있음" if cal.exists() else "없음 — topic-planner 미실행"))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main(sys.argv[1:])
