"""근로소득 세금 계산 모델 + 글별 계산 명세(content/naver/_calc/NN.json) 재계산.

45편(성과급 세금)이 검사를 다 통과했는데 내용이 틀렸다(2026-11-20). 950만원은 근로소득금액 증가였는데 '과세표준'이라 썼고,
'과세표준 증가 × 세율'을 '최종 소득세'라 불렀고, 표의 6%·24% 행은 가정과 맞지 않거나 구간을 넘었다.
검사기가 곱셈만 보고 개념과 누진 구간을 보지 않았다. 그래서 개념을 따로 두고, 증가 세액은 늘 '후 − 전'으로만 센다.

    python -X utf8 tax_calc.py --selftest     # 조문 표에서 손으로 계산한 기대값(원고 숫자를 복사하지 않는다)
    python -X utf8 tax_calc.py spec 45         # 명세의 outputs를 다시 계산해 다르면 종료 코드 1

간이세액표(원천징수액)는 구현하지 않는다 — 원천징수액 예시는 not_run이다.
"""
import json
import math
import re
import sys
from pathlib import Path

CALC_DIR = Path(__file__).parent / "content" / "naver" / "_calc"

# 소득세법 제47조 제1항(2026-11-19 확인, CaseNote 원문 표): (구간 하한, 고정 공제, 초과분 비율). 상한 2천만원
EARNED_DEDUCTION = [(0, 0, 0.70), (5_000_000, 3_500_000, 0.40), (15_000_000, 7_500_000, 0.15),
                    (45_000_000, 12_000_000, 0.05), (100_000_000, 14_750_000, 0.02)]
# 소득세법 제55조 제1항(2026-11-18 확인): (구간 하한, 그 하한까지의 세액, 세율). 3억원 초과 구간은 원문 확인 전이라 두지 않는다
TAX_TABLE = [(0, 0, 0.06), (14_000_000, 840_000, 0.15), (50_000_000, 6_240_000, 0.24),
             (88_000_000, 15_360_000, 0.35)]
TAX_TABLE_MAX = 150_000_000      # ponytail: 1억5천만원 초과 구간(38%~)은 원문을 아직 안 봤다. 넘으면 예외 — 필요할 때 원문 확인 후 추가


def earned_income_deduction(total_pay: int) -> int:
    """근로소득공제(제47조). 총급여가 공제액보다 작으면 총급여(제3항)."""
    floor, base, rate = max(t for t in EARNED_DEDUCTION if t[0] <= total_pay)
    return min(int(base + (total_pay - floor) * rate), 20_000_000, total_pay)


def income_tax(taxable: int) -> int:
    """종합소득산출세액(제55조). 누진 구간 함수 — 한계세율 곱으로 증가분을 세지 않는다."""
    if taxable > TAX_TABLE_MAX:
        raise ValueError(f"과세표준 {taxable:,}원은 확인한 세율표 범위(1억5천만원 이하)를 넘는다")
    floor, base, rate = max(t for t in TAX_TABLE if t[0] <= max(taxable, 0))
    return int(base + (max(taxable, 0) - floor) * rate)


def earned_income_credit(calc_tax: int, total_pay: int) -> int:
    """근로소득세액공제(제59조, 2026-11-20 CaseNote 원문). 근로소득만 있다고 보고 산출세액 전체에 적용한다."""
    raw = calc_tax * 0.55 if calc_tax <= 1_300_000 else 715_000 + (calc_tax - 1_300_000) * 0.30
    if total_pay <= 33_000_000:
        cap = 740_000
    elif total_pay <= 70_000_000:
        cap = max(740_000 - (total_pay - 33_000_000) * 8 / 1000, 660_000)
    elif total_pay <= 120_000_000:
        cap = max(660_000 - (total_pay - 70_000_000) / 2, 500_000)
    else:
        cap = max(500_000 - (total_pay - 120_000_000) / 2, 200_000)
    return int(min(raw, cap))


def card_deduction(total_pay: int, credit_use: int, kids: int = 0, debit_use: int = 0) -> int:
    """신용카드 소득공제(조세특례제한법 제126조의2, 2026-11-20 확인) — 신용카드·직불카드등만 있는 경우.
    공제 = 신용 × 15% + 직불 × 30% − 제2항 제6호 금액(가목: 문턱 ≤ 신용이면 문턱 × 15%, 나목: 신용 × 15% + (문턱 − 신용) × 30%). 한도 제10항.
    ponytail: 전통시장·대중교통·문화체육(제6호 다목, 제11항 추가 한도)은 안 다룬다 — 그런 예시를 쓸 때 넓힌다"""
    threshold = total_pay * 25 // 100
    if credit_use + debit_use <= threshold:
        return 0
    minus = threshold * 0.15 if threshold <= credit_use else credit_use * 0.15 + (threshold - credit_use) * 0.30
    amount = int(credit_use * 0.15 + debit_use * 0.30 - minus)
    if total_pay <= 70_000_000:
        cap = {0: 3_000_000, 1: 3_500_000}.get(kids, 4_000_000)
    else:
        cap = {0: 2_500_000, 1: 2_750_000}.get(kids, 3_000_000)
    return min(amount, cap)


def bonus_months(pay_month: int, prev_bonus_month: int = None, period_months: float = None) -> int:
    """상여 원천징수의 지급대상기간 월수(제136조 제1항). 정해진 기간이 없으면 1월(또는 직전 상여 다음 달)부터
    지급월까지. 1년 초과는 1년, 1개월 미만 끝수는 1개월(제3호)."""
    if period_months is None:
        period_months = pay_month - (prev_bonus_month or 0)
    return min(math.ceil(period_months), 12)


def year_tax(total_pay: int, other_deductions: int = 0, credit_use: int = 0, other_credits: int = 0, kids: int = 0,
             debit_use: int = 0) -> dict:
    """한 해 근로소득세를 개념별로 따로 낸다. 국세(소득세)만이다 — 지방소득세·사회보험료는 계산하지 않는다."""
    ded = earned_income_deduction(total_pay)
    earned = total_pay - ded
    card = card_deduction(total_pay, credit_use, kids, debit_use)
    taxable = max(earned - other_deductions - card, 0)
    calc = income_tax(taxable)
    credit = earned_income_credit(calc, total_pay)
    decided = max(calc - credit - other_credits, 0)
    return {"총급여": total_pay, "근로소득공제": ded, "근로소득금액": earned, "카드공제": card,
            "기타소득공제": other_deductions, "과세표준": taxable, "산출세액": calc,
            "근로소득세액공제": credit, "기타세액공제": other_credits, "결정세액": decided}


def run_spec(spec: dict) -> dict:
    """명세의 scenarios를 year_tax로 계산하고 outputs의 expr('after.산출세액 - before.산출세액')을 평가한다."""
    res = {name: year_tax(**sc["inputs"]) for name, sc in spec["scenarios"].items()}
    out = {}
    for o in spec["outputs"]:
        expr = re.sub(r"(\w+)\.(\w+)", lambda m: repr(res[m.group(1)][m.group(2)]), o["expr"])
        if not re.fullmatch(r"[\d\s+\-*/().]+", expr):
            raise ValueError(f"{o['id']}: 계산식에 허용되지 않은 기호 — {o['expr']}")
        out[o["id"]] = int(round(eval(expr)))      # 숫자·사칙연산만 남은 것을 위에서 확인했다
    return out


def spec_issues(nn: str) -> list:
    """명세를 다시 계산해 outputs.value와 다르면 문제 목록. 명세가 없으면 빈 목록."""
    p = CALC_DIR / f"{nn}.json"
    if not p.exists():
        return []
    spec = json.loads(p.read_text(encoding="utf-8"))
    got = run_spec(spec)
    return [f"계산 명세 {nn}: {o['id']} 기록 {o['value']:,}원 ≠ 재계산 {got[o['id']]:,}원"
            for o in spec["outputs"] if got[o["id"]] != o["value"]]


def selftest():
    # 제47조: 5천만원 = 1,200만 + (5,000만−4,500만)×5% = 1,225만 / 6천만원 = 1,200만 + 1,500만×5% = 1,275만
    assert earned_income_deduction(50_000_000) == 12_250_000
    assert earned_income_deduction(60_000_000) == 12_750_000
    # 구간 경계: 4,500만원은 750만 + 3,000만×15% = 1,200만, 4,500만+1원부터 5% 구간
    assert earned_income_deduction(45_000_000) == 12_000_000
    assert earned_income_deduction(46_000_000) == 12_050_000          # 1,200만 + 100만×5%
    assert earned_income_deduction(400_000_000) == 20_000_000         # 상한
    # 제55조: 3,000만 = 84만 + 1,600만×15% = 324만 / 3,950만 = 84만 + 2,550만×15% = 466.5만 → 같은 구간 증가 142.5만
    assert income_tax(30_000_000) == 3_240_000 and income_tax(39_500_000) == 4_665_000
    # 경계 넘음: 4,500만 = 84만 + 3,100만×15% = 549만 / 5,450만 = 624만 + 450만×24% = 732만 → 183만(950만×15%=142.5만이 아니다)
    assert income_tax(54_500_000) - income_tax(45_000_000) == 1_830_000
    assert income_tax(10_000_000) == 600_000 and income_tax(0) == 0
    # 제59조: 산출 324만 → 71.5만 + 194만×30% = 129.7만, 한도 74만 − 1,700만×8/1000 = 60.4만 → 66만 하한 → 66만
    assert earned_income_credit(3_240_000, 50_000_000) == 660_000
    # 총급여 8천만: 한도 66만 − 1,000만/2 → 50만 하한 / 총급여 7천만: 74만 − 3,700만×8/1000 = 44.4만 → 66만
    assert earned_income_credit(5_490_000, 70_000_000) == 660_000 and earned_income_credit(7_320_000, 80_000_000) == 500_000
    assert earned_income_credit(1_000_000, 30_000_000) == 550_000      # 130만 이하 55%
    # 제126조의2: 신용 2,000만, 총급여 5천만 → (2,000만 − 1,250만)×15% = 112.5만 / 6천만 → (2,000만 − 1,500만)×15% = 75만
    assert card_deduction(50_000_000, 20_000_000) == 1_125_000 and card_deduction(60_000_000, 20_000_000) == 750_000
    assert card_deduction(50_000_000, 10_000_000) == 0                 # 문턱 아래
    assert card_deduction(50_000_000, 60_000_000) == 3_000_000         # 한도 300만
    # 가목: 신용 1,500만 + 체크 500만, 문턱 1,250만 ≤ 신용 → 225만 + 150만 − 187.5만 = 187.5만
    assert card_deduction(50_000_000, 15_000_000, debit_use=5_000_000) == 1_875_000
    # 나목: 신용 1,000만 + 체크 1,000만, 문턱 1,250만 > 신용 → 150만 + 300만 − (150만 + 250만 × 30%) = 225만
    assert card_deduction(50_000_000, 10_000_000, debit_use=10_000_000) == 2_250_000
    # 근로소득금액 증가 ≠ 과세표준 증가: 카드 공제가 줄면 과세표준이 더 늘어난다
    a, b = year_tax(50_000_000, 7_750_000, 20_000_000), year_tax(60_000_000, 7_750_000, 20_000_000)
    assert b["근로소득금액"] - a["근로소득금액"] == 9_500_000
    assert b["과세표준"] - a["과세표준"] == 9_875_000                  # 950만 + (112.5만 − 75만)
    # 다른 공제 변화 없음: 과세표준 3,000만 → 3,950만, 산출 +142.5만, 근로소득세액공제 66만 → 66만이라 결정세액도 +142.5만
    a, b = year_tax(50_000_000, 7_750_000), year_tax(60_000_000, 7_750_000)
    assert (a["과세표준"], b["과세표준"]) == (30_000_000, 39_500_000)
    assert b["결정세액"] - a["결정세액"] == b["산출세액"] - a["산출세액"] == 1_425_000
    # 산출세액 ≠ 결정세액 변화: 총급여 7천만 → 8천만, 과세표준 4,500만 → 5,450만. 산출 +183만, 세액공제 66만 → 50만이라 결정 +199만
    a, b = year_tax(70_000_000, 11_750_000), year_tax(80_000_000, 11_750_000)
    assert (a["과세표준"], b["과세표준"]) == (45_000_000, 54_500_000)
    assert b["산출세액"] - a["산출세액"] == 1_830_000 and b["결정세액"] - a["결정세액"] == 1_990_000
    # 제136조: 기간 없는 12월 성과급 → 1~12월 12개월 / 6월에 받고 12월에 또 → 7~12월 6개월 / 정해진 6개월 / 18개월은 12 / 2.3개월은 3
    assert bonus_months(12) == 12 and bonus_months(12, 6) == 6 and bonus_months(12, period_months=6) == 6
    assert bonus_months(12, period_months=18) == 12 and bonus_months(3, period_months=2.3) == 3
    try:
        income_tax(200_000_000)
        raise AssertionError("확인하지 않은 구간을 조용히 계산했다")
    except ValueError:
        pass
    spec = {"scenarios": {"before": {"inputs": {"total_pay": 50_000_000, "other_deductions": 7_750_000}},
                          "after": {"inputs": {"total_pay": 60_000_000, "other_deductions": 7_750_000}}},
            "outputs": [{"id": "d", "expr": "after.산출세액 - before.산출세액", "value": 1_425_000}]}
    assert run_spec(spec) == {"d": 1_425_000}
    print("selftest ok (not_run: 간이세액표 원천징수액 — 표를 구현하지 않았다)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif len(sys.argv) > 2 and sys.argv[1] == "spec":
        issues = spec_issues(sys.argv[2])
        if not (CALC_DIR / f"{sys.argv[2]}.json").exists():
            sys.exit(f"명세 없음: {CALC_DIR / (sys.argv[2] + '.json')}")
        for i in issues:
            print("✗", i)
        print("spec ok" if not issues else f"spec 실패 {len(issues)}건")
        sys.exit(1 if issues else 0)
    else:
        print(__doc__)
