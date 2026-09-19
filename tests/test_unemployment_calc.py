"""실업급여 계산기(assets/calc/unemployment.js) 검증.

2026년 기준: 상한 68,100원 / 하한 66,048원 / 평균임금의 60% / 소정급여일수 별표1.
    python -X utf8 tests/test_unemployment_calc.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

JS = (Path(__file__).parent.parent / "assets" / "calc" / "unemployment.js").read_text(encoding="utf-8")

# (월급, 나이구분, 가입기간idx, 기대 1일급여, 기대 일수, 기대 총액, 설명)
CASES = [
    # 300만 → 일평균 98,901 → 60% 59,341 → 하한 66,048 적용, 3~5년 50세미만 180일
    (3_000_000, "under50", 2, 66_048, 180, 11_888_640, "하한 적용"),
    # 500만 → 일평균 164,835 → 60% 98,901 → 상한 68,100, 10년이상 50세미만 240일
    (5_000_000, "under50", 4, 68_100, 240, 16_344_000, "상한 적용"),
    # 350만 → 일평균 115,385 → 60% 69,231 → 상한, 50세이상 5~10년 240일
    (3_500_000, "over50", 3, 68_100, 240, 16_344_000, "50세 이상 240일"),
    # 250만 → 60% 49,451 → 하한, 1년 미만 120일
    (2_500_000, "under50", 0, 66_048, 120, 7_925_760, "1년 미만 120일"),
    # 340만 → 일평균 112,088 → 60% 67,253 → 상·하한 사이 비례 구간
    (3_400_000, "under50", 1, 67_252, 150, 10_087_912, "비례 구간"),
    # 50세 이상 10년 이상 = 270일 (최장)
    (5_000_000, "over50", 4, 68_100, 270, 18_387_000, "최장 270일"),
]


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content('<div id="jg-calc-unemp"></div>')
        page.add_script_tag(content=JS)
        failed = 0
        for pay, age, term, exp_daily, exp_days, exp_total, label in CASES:
            r = page.evaluate("([p,a,t]) => window.jgCalcUnemp(p,a,t)", [pay, age, term])
            daily, days, total = round(r["benefit"]), r["days"], round(r["total"])
            ok = abs(daily - exp_daily) <= 1 and days == exp_days and abs(total - exp_total) <= 60
            print(f"  {'OK ' if ok else 'FAIL'} {label:<14} 월 {pay:>9,} → 1일 {daily:,} (기대 {exp_daily:,}) "
                  f"/ {days}일 (기대 {exp_days}) / 총 {total:,} (기대 {exp_total:,})")
            failed += 0 if ok else 1

        # 상·하한 경계: 평균임금의 60%가 하한 미만이면 무조건 하한
        low = page.evaluate("() => window.jgCalcUnemp(1000000,'under50',0)")
        assert round(low["benefit"]) == 66_048, "하한 미적용"
        assert low["floored"] is True, "하한 플래그 오류"
        # 아주 높은 급여도 상한을 넘지 않는다
        high = page.evaluate("() => window.jgCalcUnemp(20000000,'over50',4)")
        assert round(high["benefit"]) == 68_100, "상한 미적용"
        assert high["capped"] is True, "상한 플래그 오류"
        # 상·하한 차이는 2,052원뿐이다
        assert 68_100 - 66_048 == 2_052
        b.close()
        print("실패:", failed)
        raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
