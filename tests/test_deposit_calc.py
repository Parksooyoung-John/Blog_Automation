"""예금·적금 계산기(assets/calc/deposit.js)의 계산식 검증.

실제 브라우저에서 JS를 실행해 손으로 계산한 값과 대조한다.
    python -X utf8 tests/test_deposit_calc.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

JS = (Path(__file__).parent.parent / "assets" / "calc" / "deposit.js").read_text(encoding="utf-8")
CASES = [
    # (모드, 금액, 연이율, 개월, 방식, 과세, 기대 세전이자, 기대 세후수령액)
    ("deposit", 10_000_000, 3.5, 12, "simple", "normal", 350_000, 10_296_100),
    # (1+0.035/12)^12 = 1.0355670 → 세전 355,670, 세금 54,773, 수령 10,300,896
    ("deposit", 10_000_000, 3.5, 12, "compound", "normal", 355_670, 10_300_896),
    ("deposit", 10_000_000, 3.5, 12, "simple", "free", 350_000, 10_350_000),
    # 6,000,000 + 113,750 − 17,517.5 = 6,096,232.5
    ("saving", 500_000, 3.5, 12, "simple", "normal", 113_750, 6_096_232),
    ("saving", 500_000, 3.0, 24, "simple", "normal", 375_000, 12_317_250),
    # 조합예탁금 1.4%: 이자 350,000 × 1.4% = 4,900 → 수령 10,345,100
    ("deposit", 10_000_000, 3.5, 12, "simple", "coop", 350_000, 10_345_100),
]


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content('<div id="jg-calc-deposit"></div>')
        page.add_script_tag(content=JS)
        failed = 0
        for mode, amt, rate, months, method, tax, exp_gross, exp_total in CASES:
            r = page.evaluate(
                "([m,a,r,n,me,t]) => window.jgCalcDeposit(m,a,r,n,me,t)",
                [mode, amt, rate, months, method, tax],
            )
            gross, total = round(r["gross"]), round(r["total"])
            ok = abs(gross - exp_gross) <= 2 and abs(total - exp_total) <= 2
            print(f"  {'OK ' if ok else 'FAIL'} {mode} {amt:,} {rate}% {months}개월 {method}/{tax} "
                  f"→ 세전 {gross:,} (기대 {exp_gross:,}) / 수령 {total:,} (기대 {exp_total:,})")
            failed += 0 if ok else 1
        # 비과세는 세금이 0이어야 한다
        free = page.evaluate("() => window.jgCalcDeposit('deposit',1000000,3,12,'simple','free')")
        assert round(free["tax"]) == 0, "비과세인데 세금이 붙었다"
        b.close()
        print("실패:", failed)
        raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
