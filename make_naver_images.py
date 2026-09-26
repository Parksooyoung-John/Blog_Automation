"""네이버 블로그용 이미지 생성 — 계산기 캡처 + 원본 도식.

네이버는 직접 만든 이미지를 높게 평가하고, 다른 블로그와 겹치는 무료 이미지는 불리하다.
여기서 만드는 것은 전부 우리 자산이라 저작권 문제가 없다.

    python -X utf8 make_naver_images.py
결과: assets/naver_img/*.png
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "assets" / "naver_img"
CALC_DIR = Path(__file__).parent / "assets" / "calc"
W = 860  # 네이버 본문 기준 넉넉한 폭

FONT = "'Malgun Gothic','맑은 고딕',system-ui,sans-serif"

CARD_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: {FONT}; background: #fff; }}
.card {{ width: {W}px; padding: 34px 38px; background: #fff; }}
h2 {{ font-size: 30px; color: #1a1a1a; margin-bottom: 6px; letter-spacing: -0.5px; }}
.sub {{ font-size: 16px; color: #888; margin-bottom: 24px; }}
.row {{ display: flex; align-items: center; gap: 14px; padding: 16px 18px;
        border-radius: 12px; background: #f6f8fa; margin-bottom: 10px; }}
.row .tag {{ min-width: 92px; font-size: 19px; font-weight: 700; color: #1b64da; }}
.row .txt {{ font-size: 19px; color: #333; }}
.row .num {{ margin-left: auto; font-size: 21px; font-weight: 700; color: #1a1a1a; }}
.foot {{ margin-top: 20px; font-size: 14px; color: #999; }}
.bar {{ display: flex; height: 84px; border-radius: 10px; overflow: hidden; margin: 10px 0 14px; }}
.seg {{ display: flex; flex-direction: column; align-items: center; justify-content: center;
        gap: 3px; text-align: center; line-height: 1.3;
        font-size: 16px; font-weight: 500; color: #fff; }}
.seg b {{ font-size: 18px; font-weight: 700; }}
.legend {{ display: flex; gap: 22px; font-size: 15px; color: #555; margin-top: 4px; }}
.legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; }}
"""


def card_html(body: str) -> str:
    return f"<style>{CARD_CSS}</style><div class='card'>{body}</div>"


CARDS = {
    "01_근로장려금_가구유형": card_html("""
      <h2>근로장려금 가구 유형별 기준</h2>
      <p class='sub'>2025년 소득 기준 · 국세청 신청자격</p>
      <div class='row'><span class='tag'>단독</span><span class='txt'>연 소득 2,200만 원 미만</span><span class='num'>최대 165만 원</span></div>
      <div class='row'><span class='tag'>홑벌이</span><span class='txt'>연 소득 3,200만 원 미만</span><span class='num'>최대 285만 원</span></div>
      <div class='row'><span class='tag'>맞벌이</span><span class='txt'>연 소득 4,400만 원 미만</span><span class='num'>최대 330만 원</span></div>
      <p class='foot'>배우자 총급여 300만 원을 기준으로 홑벌이와 맞벌이가 갈립니다.</p>
    """),
    "02_근로장려금_재산구간": card_html("""
      <h2>재산이 얼마면 깎이나</h2>
      <p class='sub'>가구원 전체 합계 · 2025년 6월 1일 기준</p>
      <div class='bar'>
        <div class='seg' style='flex:1.5;background:#1b64da;'>1.7억 미만<br><b>전액 지급</b></div>
        <div class='seg' style='flex:1;background:#f59f00;'>1.7억~2.4억<br><b>50%만 지급</b></div>
        <div class='seg' style='flex:1;background:#e03131;'>2.4억 이상<br><b>지급 없음</b></div>
      </div>
      <div class='row'><span class='txt'>전세보증금도 재산에 포함됩니다</span></div>
      <div class='row'><span class='txt'>대출은 빼주지 않습니다</span></div>
      <p class='foot'>보증금 2억 원에 대출 1억 5천만 원이 있어도 재산은 2억 원으로 잡힙니다.</p>
    """),
    "03_실업급여_180일": card_html("""
      <h2>180일은 달력 6개월이 아닙니다</h2>
      <p class='sub'>피보험단위기간 · 보수를 받은 날만 계산</p>
      <div class='row'><span class='tag'>주 6일</span><span class='txt'>일요일만 유급인 주 5일제</span><span class='num'>약 7개월</span></div>
      <div class='row'><span class='tag'>주 7일</span><span class='txt'>토·일 모두 유급</span><span class='num'>약 6개월</span></div>
      <div class='row'><span class='tag'>주 4일</span><span class='txt'>주 3일 근무</span><span class='num'>약 10개월</span></div>
      <p class='foot'>무급휴일과 무급 결근은 빠집니다. 이직일 이전 18개월 안에서 합산합니다.</p>
    """),
    "04_실업급여_상하한": card_html("""
      <h2>2026년 구직급여, 하루 얼마</h2>
      <p class='sub'>상한과 하한의 차이가 2,052원뿐입니다</p>
      <div class='row'><span class='tag'>상한</span><span class='txt'>평균임금의 60%가 이보다 높아도</span><span class='num'>68,100원</span></div>
      <div class='row'><span class='tag'>하한</span><span class='txt'>평균임금의 60%가 이보다 낮아도</span><span class='num'>66,048원</span></div>
      <p class='foot'>월급 200만 원과 300만 원의 하루 금액이 같습니다. 총액은 소정급여일수가 가릅니다.</p>
    """),
    "08_근로장려금_제외대상": card_html("""
      <h2>소득·재산을 통과해도 탈락하는 경우</h2>
      <p class='sub'>근로장려금 신청 제외 대상 · 국세청 신청자격</p>
      <div class='row'><span class='tag'>전문직</span><span class='txt'>본인이나 배우자가 변호사·세무사·의사·약사 등</span></div>
      <div class='row'><span class='tag'>부양가족</span><span class='txt'>다른 사람의 부양가족으로 등록되어 있는 경우</span></div>
      <div class='row'><span class='tag'>고소득</span><span class='txt'>월 평균 근로소득 500만 원 이상인 상용근로자</span></div>
      <p class='foot'>사회초년생은 두 번째가 자주 걸립니다. 부모님 연말정산에 올라가 있으면 본인 소득과 무관하게 제외됩니다.</p>
    """),
    "09_근로장려금_신청경로": card_html("""
      <h2>안내문이 없어도 신청되는 경로</h2>
      <p class='sub'>근로장려금 신청 방법 4가지 · 국세청</p>
      <div class='row'><span class='tag'>모바일</span><span class='txt'>안내문 문자의 링크로 접속</span><span class='num' style='color:#e03131;'>안내문 필요</span></div>
      <div class='row'><span class='tag'>ARS</span><span class='txt'>1544-9944, 인증번호 8자리 입력</span><span class='num' style='color:#e03131;'>안내문 필요</span></div>
      <div class='row'><span class='tag'>홈택스</span><span class='txt'>손택스 포함, 본인인증만 하면 됨</span><span class='num' style='color:#1b64da;'>불필요</span></div>
      <div class='row'><span class='tag'>세무서</span><span class='txt'>신분증 지참 방문</span><span class='num' style='color:#1b64da;'>불필요</span></div>
      <p class='foot'>ARS에서 막히는 이유는 입력할 인증번호가 없기 때문입니다. 홈택스로 가면 됩니다.</p>
    """),
    "10_근로장려금_미입금": card_html("""
      <h2>신청했는데 입금이 없다면</h2>
      <p class='sub'>지급일이 지난 뒤 확인하는 순서</p>
      <div class='row'><span class='tag'>계좌</span><span class='txt'>본인 명의 계좌가 정확히 등록됐는지</span></div>
      <div class='row'><span class='tag'>체납</span><span class='txt'>국세 체납이 있으면 환급액의 30% 한도로 먼저 충당</span></div>
      <div class='row'><span class='tag'>요건</span><span class='txt'>요건 미달로 제외됐는지, 사유가 화면에 표시됨</span></div>
      <p class='foot'>셋 다 홈택스 조회 화면에서 확인됩니다. 애매하면 장려금 상담센터 1566-3636.</p>
    """),
}


def find_overflow(page) -> list:
    """글자가 칸을 넘쳤는지 본다.

    2026-09 실업급여 막대 도식에서 라벨이 두 줄로 넘쳐 깨진 적이 있다. PNG는 정상적으로
    생성되므로 사람이 열어보지 않으면 모른다. 줄바꿈이 허용된 요소(.foot, .sub, .seg)는 뺀다.
    """
    return page.evaluate("""
        () => {
            const out = [];
            const card = document.querySelector('.card');
            // 칸보다 긴 글자는 .card를 가로로 밀어낸다 (.card 폭은 고정)
            if (card && card.scrollWidth > card.clientWidth + 1) {
                out.push(`가로 넘침 ${card.scrollWidth}px > ${card.clientWidth}px`);
            }
            // overflow:hidden 칸(.bar 등)에서는 넘친 글자가 그냥 잘려나간다.
            // scrollHeight로는 위아래로 삐져나간 경우를 못 잡아서 실제 좌표를 비교한다.
            document.querySelectorAll('.card *').forEach(box => {
                if (getComputedStyle(box).overflow === 'visible') return;
                const b = box.getBoundingClientRect();
                // 잘려나가는 것은 대개 태그 없는 텍스트 노드라 Range로 재야 잡힌다
                const walk = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
                const range = document.createRange();
                let node;
                while ((node = walk.nextNode())) {
                    if (!node.textContent.trim()) continue;
                    range.selectNodeContents(node);
                    const r = range.getBoundingClientRect();
                    if (r.height === 0) continue;
                    if (r.top < b.top - 1 || r.bottom > b.bottom + 1 ||
                        r.left < b.left - 1 || r.right > b.right + 1) {
                        out.push('잘림: ' + node.textContent.trim().slice(0, 24));
                    }
                }
            });
            return out;
        }
    """)


def shoot_cards(page) -> list:
    broken = []
    for name, html in CARDS.items():
        page.set_viewport_size({"width": W, "height": 700})
        page.set_content(html)
        page.wait_for_timeout(400)
        over = find_overflow(page)
        el = page.query_selector(".card")
        el.screenshot(path=str(OUT / f"{name}.png"))
        if over:
            broken.append((name, over))
            print("  카드:", name, "⚠ 글자 넘침:", " / ".join(over))
        else:
            print("  카드:", name)
    return broken


def shoot_calc(page, js_file: str, container_id: str, fills: list, out_name: str):
    """계산기를 빈 페이지에 띄워 위젯만 캡처한다(티스토리 UI 없이 깨끗하게)."""
    js = (CALC_DIR / js_file).read_text(encoding="utf-8")
    page.set_viewport_size({"width": W, "height": 900})
    page.set_content(
        f"<style>body{{font-family:{FONT};background:#fff;padding:14px;}}</style>"
        f"<div id='{container_id}'></div>"
    )
    page.add_script_tag(content=js)
    page.wait_for_timeout(500)
    for sel, val, kind in fills:
        if kind == "fill":
            page.fill(sel, val)
            page.dispatch_event(sel, "input")
        else:
            page.select_option(sel, val)
        page.wait_for_timeout(200)
    page.wait_for_timeout(400)
    page.query_selector(f"#{container_id}").screenshot(path=str(OUT / out_name))
    print("  계산기:", out_name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        page = b.new_page(device_scale_factor=2)  # 선명하게

        broken = shoot_cards(page)

        shoot_calc(page, "deposit.js", "jg-calc-deposit",
                   [("#jg-amt", "10000000", "fill"), ("#jg-rate", "3.5", "fill"),
                    ("#jg-months", "12", "fill")],
                   "05_예금계산기_1000만원.png")

        shoot_calc(page, "unemployment.js", "jg-calc-unemp",
                   [("#jg-pay", "3000000", "fill"), ("#jg-term", "2", "select")],
                   "06_실업급여계산기_월300만원.png")

        shoot_calc(page, "unemployment.js", "jg-calc-unemp",
                   [("#jg-pay", "5000000", "fill"), ("#jg-term", "4", "select")],
                   "07_실업급여계산기_월500만원.png")

        b.close()
    print(f"\n완료: {OUT}")


if __name__ == "__main__":
    main()
