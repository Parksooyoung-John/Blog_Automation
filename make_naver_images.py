"""네이버 블로그용 이미지 생성 — 계산기 캡처 + 원본 도식.

네이버는 직접 만든 이미지를 높게 평가하고, 다른 블로그와 겹치는 무료 이미지는 불리하다.
여기서 만드는 것은 전부 우리 자산이라 저작권 문제가 없다.

    python -X utf8 make_naver_images.py
결과: assets/naver_img/*.png
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from naver_paste import PALETTE

OUT = Path(__file__).parent / "assets" / "naver_img"
CALC_DIR = Path(__file__).parent / "assets" / "calc"
W = 860  # 네이버 본문 기준 넉넉한 폭

FONT = "'Malgun Gothic','맑은 고딕',system-ui,sans-serif"

CARD_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: {FONT}; background: #fff; }}
.card {{ width: {W}px; padding: 34px 0; background: #fff; word-break: keep-all; }}  /* 좌우 여백 0: 블로그 본문 폭에 꽉 차게(2026-10-15 사용자 요청 — 38px 여백 때문에 구분선보다 좁아 보였다) */
h2 {{ font-size: 30px; color: #1a1a1a; margin-bottom: 6px; letter-spacing: -0.5px; word-break: keep-all; }}
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

/* 계산 흐름(공식) 카드 — 단계를 화살표로 잇는다 */
.flow {{ display: flex; align-items: stretch; gap: 10px; margin: 18px 0 8px; }}
.flow .step {{ flex: 1; border-radius: 16px; padding: 22px 14px; text-align: center;
               background: linear-gradient(180deg, #f8fafc 0%, #eef1f5 100%);
               border: 1px solid #e8ebef; }}
.flow .step .k {{ font-size: 13px; font-weight: 700; color: #1b64da; letter-spacing: .3px; }}
.flow .step .v {{ font-size: 23px; font-weight: 800; color: #1a1a1a; margin-top: 8px; line-height: 1.25; }}
.flow .step .d {{ font-size: 13px; color: #868e96; margin-top: 6px; }}
.flow .arrow {{ display: flex; align-items: center; font-size: 24px; color: #ced4da; font-weight: 700; }}
.range {{ display: flex; gap: 12px; margin: 4px 0 14px; }}
.range .pill {{ flex: 1; border-radius: 14px; padding: 16px 18px; color: #fff; }}
.range .pill .t {{ font-size: 14px; opacity: .9; font-weight: 600; }}
.range .pill .n {{ font-size: 26px; font-weight: 800; margin-top: 4px; }}
.range .gap {{ text-align: center; align-self: center; font-size: 14px; color: #999; min-width: 90px; }}

/* 예시 비교 카드 — 세 금액을 나란히 */
.exgrid {{ display: flex; gap: 14px; margin: 6px 0 10px; }}
.exgrid .ex {{ flex: 1; border-radius: 16px; padding: 20px 16px; background: #fff;
               border: 1px solid #eceef1; box-shadow: 0 3px 14px rgba(20,30,50,.06); }}
.exgrid .ex .badge {{ display: inline-block; padding: 5px 12px; border-radius: 20px;
                       font-size: 13px; font-weight: 700; color: #fff; }}
.exgrid .ex .pay {{ font-size: 15px; color: #868e96; margin-top: 12px; }}
.exgrid .ex .amt {{ font-size: 25px; font-weight: 800; color: #1a1a1a; margin-top: 3px; }}
.exgrid .ex .note {{ font-size: 12.5px; color: #adb5bd; margin-top: 10px; line-height: 1.5; }}

/* 2026-10-09 추가 형태 4종 — 강조색(--accent) 머리띠가 붙는다. 기존 카드는 이 규칙을 쓰지 않는다 */
.band {{ height: 10px; border-radius: 6px; margin-bottom: 22px; background: var(--accent); }}
.hero {{ display: flex; align-items: baseline; gap: 12px; margin: 10px 0 4px; }}
.hero .big {{ font-size: 96px; font-weight: 800; letter-spacing: -3px; line-height: 1; color: var(--accent); }}
.hero .unit {{ font-size: 30px; font-weight: 700; color: #333; }}
.hero-desc {{ font-size: 20px; color: #444; margin-top: 14px; line-height: 1.5; }}
.bars .b {{ margin-bottom: 16px; }}
.bars .lab {{ display: flex; justify-content: space-between; align-items: baseline;
              font-size: 18px; color: #333; margin-bottom: 7px; }}
.bars .lab b {{ font-size: 21px; color: #1a1a1a; }}
.bars .track {{ height: 26px; border-radius: 13px; background: #eef1f5; overflow: hidden; }}
.bars .fill {{ height: 100%; border-radius: 13px; background: var(--accent); }}
.tl {{ margin: 10px 0 4px 12px; padding-left: 30px; border-left: 3px solid #dfe3e8; }}
.tl .ev {{ position: relative; padding-bottom: 22px; }}
.tl .ev:last-child {{ padding-bottom: 2px; }}
.tl .ev::before {{ content: ''; position: absolute; left: -41px; top: 3px; width: 13px; height: 13px;
                   border-radius: 50%; background: var(--accent); border: 3px solid #fff;
                   box-shadow: 0 0 0 2px var(--accent); }}
.tl .when {{ font-size: 15px; font-weight: 700; color: var(--accent); }}
.tl .what {{ font-size: 20px; font-weight: 700; color: #1a1a1a; margin-top: 2px; }}
.tl .why {{ font-size: 15px; color: #777; margin-top: 3px; }}
.chk .it {{ display: flex; gap: 14px; align-items: flex-start; padding: 14px 16px;
            border-radius: 12px; background: #f6f8fa; margin-bottom: 10px; }}
.chk .box {{ flex: none; width: 26px; height: 26px; border-radius: 7px; background: var(--accent);
             color: #fff; font-size: 17px; font-weight: 800;
             display: flex; align-items: center; justify-content: center; }}
.chk .t {{ font-size: 19px; color: #222; line-height: 1.4; }}
.chk .t small {{ display: block; font-size: 14px; color: #888; margin-top: 3px; }}
"""

# 카테고리마다 강조색 하나. 흰 바탕에 회색 줄만 있던 카드가 '글 같은 이미지'로 보였다.
ACCENT = {"실업급여": "#1b64da", "근로장려금": "#12b886", "세금": "#f76707", "연금·건강보험": "#7048e8"}
CARD_ZOOM = 1.5


def post_look(num: int) -> str:
    """14편부터 카드의 accent 자리에 넣는다 — 그 글의 박스·표와 같은 색(naver_paste.PALETTE) + 글자 1.5배.

    카드는 860px로 그리지만 폰에서는 360px 안팎으로 줄어든다. 15px 설명 줄이 6px 남짓이 돼 34번 카드가 안 읽혔다.
    `_framed`의 `style='--accent:…'`에 그대로 들어가므로 색 뒤에 zoom 선언을 붙여 보낸다. 13편까지는 ACCENT 그대로다.
    """
    return f"{PALETTE[num % len(PALETTE)][1]};zoom:{CARD_ZOOM}"


def card_html(body: str) -> str:
    return f"<style>{CARD_CSS}</style><div class='card'>{body}</div>"


def _framed(accent: str, title: str, sub: str, inner: str, foot: str) -> str:
    return card_html(f"<div style='--accent:{accent}'><div class='band'></div><h2>{title}</h2>"
                     f"<p class='sub'>{sub}</p>{inner}<p class='foot'>{foot}</p></div>")


class Card(str):
    """HTML 카드 + 만든 재료. `--canva-data`가 같은 재료로 Canva 템플릿을 채운다."""
    kind: str
    args: tuple


def _card(html: str, kind: str, *args) -> Card:
    c = Card(html)
    c.kind, c.args = kind, args
    return c


def hero_card(accent, title, sub, big, unit, desc, foot) -> str:
    """답이 되는 숫자 하나를 크게."""
    return _card(_framed(accent, title, sub, f"<div class='hero'><span class='big'>{big}</span>"
                         f"<span class='unit'>{unit}</span></div><p class='hero-desc'>{desc}</p>", foot),
                 "hero", title, sub, big, unit, desc, foot)


def bar_card(accent, title, sub, rows, foot) -> str:
    """값의 크기 차이를 막대 길이로. rows: [(이름, 표시값, 0~100 비율)]"""
    bars = "".join(f"<div class='b'><div class='lab'><span>{n}</span><b>{v}</b></div>"
                   f"<div class='track'><div class='fill' style='width:{p}%'></div></div></div>" for n, v, p in rows)
    return _card(_framed(accent, title, sub, f"<div class='bars'>{bars}</div>", foot), "bar", title, sub, rows, foot)


def timeline_card(accent, title, sub, events, foot) -> str:
    """날짜·순서가 있는 절차. events: [(언제, 무엇, 설명)]"""
    evs = "".join(f"<div class='ev'><div class='when'>{w}</div><div class='what'>{x}</div>"
                  f"<div class='why'>{y}</div></div>" for w, x, y in events)
    return _card(_framed(accent, title, sub, f"<div class='tl'>{evs}</div>", foot), "timeline", title, sub, events, foot)


def checklist_card(accent, title, sub, items, foot) -> str:
    """확인할 것의 목록. items: [(항목, 보충 설명)]"""
    its = "".join(f"<div class='it'><div class='box'>✓</div><div class='t'>{a}<small>{b}</small></div></div>"
                  for a, b in items)
    return _card(_framed(accent, title, sub, f"<div class='chk'>{its}</div>", foot), "checklist", title, sub, items, foot)


# ── Canva 브랜드 템플릿 (18편~) ─────────────────────────────────
# 자동 채우기는 글자만 넣는다. 색·막대 길이는 채운 뒤 MCP 편집으로 바꾼다 — 그 값도 여기서 같이 낸다.
CANVA_TEMPLATES = {"hero": "EAHYLqz_cuM", "bar": "EAHYL8tWtzI", "timeline": "EAHYL4ay_c4", "checklist": "EAHYLx47n-M"}
CANVA_BAR_MAX = 657.9       # 막대 템플릿에서 100%일 때 막대 폭(px)
CANVA_MAX_LEN = {"desc": 66, "row_label": 18}   # 큰숫자 설명 3줄×22자, 막대 이름 칸 2줄×9자 — 넘치면 칸 밖으로 나간다


def _light(hex_color: str, k: float = 0.25) -> str:
    """글 색을 흰색에 섞은 연한 색 — 짧은 막대용. PALETTE의 배경색은 흰 카드에서 안 보일 만큼 옅다."""
    rgb = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(c * k + 255 * (1 - k)):02x}" for c in rgb)


def canva_fields(card: Card) -> dict:
    """카드 재료 → 템플릿 필드. 템플릿 칸 수와 안 맞으면 ValueError — 칸이 남거나 모자라면 시안 글자가 그대로 남는다."""
    k, a = card.kind, card.args
    if k == "hero":
        title, sub, big, unit, desc, foot = a
        if len(str(big)) > 2:      # 3자리부터 숫자가 오른쪽 단위·설명을 덮었다(큰숫자 템플릿 시험)
            raise ValueError(f"큰 숫자는 2자리까지: {big}")
        if len(desc) > CANVA_MAX_LEN["desc"]:
            raise ValueError(f"설명 {len(desc)}자 > {CANVA_MAX_LEN['desc']}자: {desc}")
        return {"title": title, "sub": sub, "big": str(big), "unit": unit, "desc": desc, "foot": foot}
    title, sub, rows, foot = a
    need = {"bar": 2, "timeline": 4, "checklist": 3}[k]
    if len(rows) != need:
        raise ValueError(f"{k} 템플릿은 {need}칸인데 {len(rows)}개다")
    f = {"title": title, "sub": sub, "foot": foot}
    for i, r in enumerate(rows, 1):
        if k == "bar":
            if len(r[0]) > CANVA_MAX_LEN["row_label"]:
                raise ValueError(f"막대 이름 {len(r[0])}자 > {CANVA_MAX_LEN['row_label']}자: {r[0]}")
            f[f"row{i}_label"], f[f"row{i}_value"] = r[0], r[1]
        elif k == "timeline":
            f[f"step{i}"] = f"{r[0]}\n{r[1]}"     # 설명(r[2])은 칸이 좁아 뺀다
        else:
            f[f"item{i}"], f[f"item{i}_desc"] = r
    return f


def canva_data(num: int) -> list:
    """그 편 원고에 자리가 있는 카드들의 템플릿 ID·필드·색. 세션에서 이 값으로 자동 채우기 → 색 → 내보내기를 한다."""
    md = draft_md(f"{num:02d}")
    _, main_c, _ = PALETTE[num % len(PALETTE)]
    out = []
    for name, card in CARDS.items():
        if f"{name}.png" not in md or not isinstance(card, Card):
            continue
        item = {"card": name, "kind": card.kind, "template": CANVA_TEMPLATES[card.kind],
                "fields": canva_fields(card), "color": main_c}
        if card.kind == "bar":
            item["light"] = _light(main_c)
            item["bar_widths"] = [round(CANVA_BAR_MAX * r[2] / 100, 1) for r in card.args[2]]
        out.append(item)
    return out


def canva_selftest():
    h = hero_card("#000", "제목", "부제", "10", "년", "설명", "주석")
    assert canva_fields(h) == {"title": "제목", "sub": "부제", "big": "10", "unit": "년", "desc": "설명", "foot": "주석"}
    b = bar_card("#000", "t", "s", [("가", "18만원", 57), ("나", "31만원", 100)], "f")
    assert canva_fields(b)["row2_value"] == "31만원" and b.args[2][0][2] == 57
    t = timeline_card("#000", "t", "s", [("1월", "내기", "x"), ("2월", "확정", "y"), ("3월", "받기", "z"), ("4월", "끝", "w")], "f")
    assert canva_fields(t)["step3"] == "3월\n받기"
    c = checklist_card("#000", "t", "s", [("a", "a설명"), ("b", "b설명"), ("c", "c설명")], "f")
    assert canva_fields(c)["item2_desc"] == "b설명"
    for bad in (hero_card("#000", "t", "s", "843", "만원", "d", "f"),
                checklist_card("#000", "t", "s", [("a", "b")], "f"),
                hero_card("#000", "t", "s", "3", "년", "가" * 67, "f"),
                bar_card("#000", "t", "s", [("총급여 6,000만원인 사람이 냄 (문턱 180만원)", "18만원", 57), ("나", "1", 100)], "f")):
        try:
            canva_fields(bad)
            raise AssertionError("칸 수·자릿수 위반을 못 잡음")
        except ValueError:
            pass
    assert _light("#1a5276") == "#c6d4dd"
    assert isinstance(CARDS["40_노령연금_기간채우기"], Card) and set(CANVA_TEMPLATES) == {"hero", "bar", "timeline", "checklist"}
    print("selftest OK")


# ── 제목 썸네일 ──────────────────────────────────────────────────
# 정사각형으로 만든다. 12편 썸네일은 가로형(16:9)에 글자를 왼쪽 아래에 뒀는데, 네이버가 목록용으로
# 정사각형으로 자르면서(인물 쪽으로 치우쳐 자른다) 글자가 "…가족 / …만원이 기준입니다"만 남았다.
# 정사각형 원본은 정사각형으로 쓸 때 안 잘리고, 가로로 잘릴 때는 가운데 띠만 남으므로 글자를 그 띠 안에 둔다.
THUMB = 860
BAND = (188, 672)          # 16:9로 가운데를 잘랐을 때 남는 세로 구간
SIDE = 120                 # 글자 좌우 여백
THUMB_FONT = "Jalnan2TTF.ttf"      # 여기어때 잘난체 2
FONT_DIRS = [Path.home() / "AppData/Local/Microsoft/Windows/Fonts", Path("C:/Windows/Fonts")]

THUMB_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Thumb'; }
.thumb { width: %(size)dpx; height: %(size)dpx; position: relative; background-size: cover; background-position: center; }
.thumb::after { content: ''; position: absolute; inset: 0;
                background: linear-gradient(180deg, rgba(0,0,0,.04) 34%%, rgba(0,0,0,.74) 66%%, rgba(0,0,0,.34) 100%%); }
.thumb .txt { position: absolute; left: %(side)dpx; right: %(side)dpx; bottom: %(bottom)dpx; z-index: 1; text-align: center; }
.thumb .l1, .thumb .l2 { -webkit-text-stroke: 11px #111; paint-order: stroke fill; white-space: nowrap; }
.thumb .l1 { font-size: 62px; color: #fff; }
.thumb .l2 { font-size: 84px; color: #ffe033; line-height: 1.12; margin-top: 6px; }
""" % {"size": THUMB, "side": SIDE, "bottom": THUMB - BAND[1] + 24}


def thumb_font() -> Path:
    """썸네일 폰트 파일. 없으면 멈춘다 — 조용히 맑은 고딕으로 바뀌면 썸네일마다 글씨가 달라진다."""
    for d in FONT_DIRS:
        if (d / THUMB_FONT).exists():
            return d / THUMB_FONT
    raise SystemExit(f"썸네일 폰트 {THUMB_FONT}(여기어때 잘난체 2)를 찾지 못했습니다. "
                     f"설치 위치: {' 또는 '.join(str(d) for d in FONT_DIRS)}")


def thumb_text(md: str):
    """원고 작성 메모의 `- 썸네일 문구: 윗줄 | 아랫줄` → (윗줄, 아랫줄). 없으면 None.
    줄 안의 `/`는 줄바꿈이다(정사각형 폭에는 큰 글자 7~8자가 한계)."""
    import re
    m = re.search(r"^- 썸네일 문구:\s*(.+?)\s*\|\s*(.+?)\s*$", md, flags=re.M)
    return (m.group(1), m.group(2)) if m else None


def shoot_thumb(page, photo: Path, line1: str, line2: str, out: Path, font: Path = None, crop_preview: Path = None):
    """대표 사진 위에 제목 문구를 얹은 정사각형 썸네일. 사진은 사용자가 고른 것만 쓴다(AI 생성 없음).
    → 글자가 좌우 여백과 가로 크롭 띠 안에 다 들어갔으면 True"""
    import base64
    import html as html_lib
    font = font or thumb_font()
    mime = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}[photo.suffix.lower()]
    face = (f"@font-face {{ font-family: 'Thumb'; "
            f"src: url(data:font/ttf;base64,{base64.b64encode(font.read_bytes()).decode()}); }}")
    lines = ["<br>".join(html_lib.escape(part.strip()) for part in t.split("/")) for t in (line1, line2)]
    page.set_viewport_size({"width": THUMB, "height": THUMB})
    page.set_content(f"<style>{face}{THUMB_CSS}</style><div class='thumb' style=\"background-image:"
                     f"url('data:image/{mime};base64,{base64.b64encode(photo.read_bytes()).decode()}')\">"
                     f"<div class='txt'><div class='l1'>{lines[0]}</div><div class='l2'>{lines[1]}</div></div></div>")
    page.evaluate("() => document.fonts.ready")
    page.wait_for_timeout(500)
    # 글자의 실제 좌표를 잰다. 외곽선 두께(11px의 절반)만큼 여유를 둔다
    box = page.evaluate("""() => {
        const r = document.createRange(); let l = 1e9, t = 1e9, rt = -1e9, b = -1e9;
        document.querySelectorAll('.l1, .l2').forEach(el => { r.selectNodeContents(el);
            for (const q of r.getClientRects()) { l = Math.min(l, q.left); t = Math.min(t, q.top);
                                                  rt = Math.max(rt, q.right); b = Math.max(b, q.bottom); } });
        return {l, t, r: rt, b, font: document.fonts.check("52px Thumb")};
    }""")
    page.query_selector(".thumb").screenshot(path=str(out))
    if crop_preview:
        page.screenshot(path=str(crop_preview), clip={"x": 0, "y": BAND[0], "width": THUMB, "height": BAND[1] - BAND[0]})
    problems = []
    if not box["font"]:
        problems.append("폰트가 적용되지 않았다")
    if box["l"] < SIDE - 6 or box["r"] > THUMB - SIDE + 6:
        problems.append(f"글자가 좌우 여백을 넘는다 (폭 {box['r'] - box['l']:.0f}px, 한도 {THUMB - 2 * SIDE}px) — `/`로 줄을 나누거나 줄인다")
    if box["t"] < BAND[0] + 12 or box["b"] > BAND[1] - 6:
        problems.append("글자가 가로 크롭 띠를 벗어난다 — 줄 수를 줄인다")
    for x in problems:
        print(f"  ⚠ 썸네일: {x}  [{line1} | {line2}]")
    return not problems


# ── 15편~ 썸네일 두 유형 (NAVER_GUIDE 「벤치마크 템플릿 시험」) ─────────────
# scene: 벤치마크(sky09020) 대표 이미지는 Gemini가 글자까지 그린 그림이다(구석에 Gemini 표시가 남아 있었다).
#        글꼴을 얹어 흉내 내지 않고 같은 방식으로 만든다 — `--prompt NN`이 프롬프트를 내고, 코드는 정사각형 맞춤과 AI 표시만 한다.
# card:  사진 위에 카드를 코드로 얹는다. 글꼴은 상업 이용이 확인된 잘난체 2(G마켓 산스는 라이선스 원문을 못 찾았다, 2026-10-14).
OLIVE, CORAL = "#556b2f", "#ff6f61"

# 그림체는 2026-10-14 컨셉 시험에서 S1(반실사 페인팅 + 새싹돼지 조연)으로 정했다 — NAVER_GUIDE 「썸네일 컨셉 결정」.
# 새싹돼지는 글마다 같은 모습이어야 해서 MASCOT 문구를 바꾸지 않는다.
MASCOT = ("a chubby pastel-pink baby piglet with a small two-leaf green sprout on its head, "
          "round black eyes, rosy cheeks, tiny olive-green scarf")
SCENE_PROMPT = """Square 1:1 image, semi-realistic Korean webtoon digital painting with realistic human proportions and detailed faces, soft painterly shading, cinematic warm indoor lighting, olive, beige and coral tones.
A small cute mascot character appears beside the people, reacting to the situation, drawn in a soft 3D-like style that blends into the scene: """ + MASCOT + """.
Scene: {scene}
Composition: {composition}
Do not use the pose of resting the chin on a hand, and do not default to people sitting at a dining table.
Generic characters only (no real people), no brand logos, no real company or government names, marks or documents.
Keep the top 28% of the image a calm, uncluttered background for the title.
Title at the top, centered, in a heavy, clean Korean gothic typeface with a thick white outline and a soft drop shadow:
Line 1 — large, about 9% of the image height, color {color}: "{line1}"
Line 2 — about half the size of line 1, color #1a1a1a: "{line2}"
Render the Korean title exactly as written. No other text, numbers or labels anywhere in the image."""


def memo_value(md: str, key: str):
    import re
    m = re.search(rf"^- {re.escape(key)}:\s*(.+?)\s*$", md, flags=re.M)
    return m.group(1) if m else None


# 15~17편 썸네일이 전부 '식탁에 앉아 턱 괴고 종이·폰 보기'였다(2026-10-16 사용자 지적). 구도를 작성 메모에서 고르고
# 바로 앞 편과 같은 구도는 check_naver가 막는다. 목록은 check_naver.COMPOSITIONS와 같은 키를 쓴다.
from check_naver import COMPOSITIONS


def scene_prompt(md: str, num: int) -> str:
    line1, line2 = (t.replace("/", " ").strip() for t in thumb_text(md))
    comp = COMPOSITIONS.get(memo_value(md, "썸네일 구도") or "", "a natural, varied composition that fits the scene")
    return SCENE_PROMPT.format(scene=memo_value(md, "썸네일 장면"), composition=comp,
                               color=PALETTE[num % len(PALETTE)][1], line1=line1, line2=line2)


def _img_url(photo: Path) -> str:
    import base64
    mime = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}[photo.suffix.lower()]
    return f"data:image/{mime};base64,{base64.b64encode(photo.read_bytes()).decode()}"


def shoot_thumb_scene(page, photo: Path, out: Path):
    """Gemini 그림(글자 포함) → 정사각형 860 + 왼쪽 아래 'AI 활용' 표시. 오른쪽 아래는 Gemini 표시 자리라 피한다."""
    page.set_viewport_size({"width": THUMB, "height": THUMB})
    page.set_content(f"<style>*{{margin:0}} .t{{width:{THUMB}px;height:{THUMB}px;position:relative;background:url('{_img_url(photo)}') center/cover}}"
                     f".ai{{position:absolute;left:18px;bottom:18px;font:700 18px {FONT};color:#333;background:rgba(255,255,255,.82);"
                     f"padding:5px 12px;border-radius:14px}}</style><div class='t'><span class='ai'>AI 활용</span></div>")
    page.wait_for_timeout(300)
    page.query_selector(".t").screenshot(path=str(out))


def shoot_thumb_card(page, photo: Path, line1: str, line2: str, big: str, label: str, out: Path, font: Path = None):
    """사진(20% 어둡게) 위 흰 카드: 윗줄 올리브 글자, 아랫줄 올리브 띠, 오른쪽 아래 '예시' 서류에 코랄 원으로 숫자 강조.
    카드 글자는 가로 크롭 띠(BAND) 안에 둔다. → 글자가 카드 안에 다 들어갔으면 True"""
    import base64
    import html as html_lib
    font = font or thumb_font()
    face = f"@font-face {{ font-family: 'Thumb'; src: url(data:font/ttf;base64,{base64.b64encode(font.read_bytes()).decode()}); }}"
    e = html_lib.escape
    css = f"""{face} *{{margin:0;padding:0;box-sizing:border-box}}
.t{{width:{THUMB}px;height:{THUMB}px;position:relative;overflow:hidden;font-family:'Thumb'}}
.bg{{position:absolute;inset:0;background:url('{_img_url(photo)}') center/cover;filter:brightness(.8) blur(1.5px)}}
.card{{position:absolute;left:8%;right:8%;top:{BAND[0] + 14}px;height:236px;background:#fff;border:6px solid {OLIVE};
      border-radius:24px;box-shadow:0 10px 30px rgba(0,0,0,.28);text-align:center;overflow:hidden}}
.l1{{color:{OLIVE};font-size:76px;line-height:1.1;padding:26px 20px 0;white-space:nowrap}}
.l2{{position:absolute;left:0;right:0;bottom:0;background:{OLIVE};color:#fff;font-size:58px;line-height:1.1;padding:16px 20px 20px;white-space:nowrap}}
.mock{{position:absolute;right:5%;top:{BAND[0] + 236}px;width:46%;background:#fdfcf8;border:2px solid #d9d4c7;border-radius:14px;
      padding:22px 24px;box-shadow:0 12px 26px rgba(0,0,0,.3);transform:rotate(-3deg);font-family:{FONT}}}
.mock .tag{{display:inline-block;font:700 15px {FONT};color:#777;border:1.5px solid #bbb;border-radius:6px;padding:2px 8px}}
.mock .ln{{height:10px;background:#e6e2d8;border-radius:5px;margin:12px 0}}
.mock .row{{display:flex;justify-content:space-between;align-items:center;margin-top:16px;font:700 20px {FONT};color:#444}}
.mock .big{{font:900 34px {FONT};color:#222;border:4px solid {CORAL};border-radius:50%;padding:6px 14px}}"""
    page.set_viewport_size({"width": THUMB, "height": THUMB})
    page.set_content(f"<style>{css}</style><div class='t'><div class='bg'></div><div class='card'>"
                     f"<div class='l1'>{e(line1)}</div><div class='l2'>{e(line2)}</div></div>"
                     f"<div class='mock'><span class='tag'>예시</span><div class='ln'></div><div class='ln' style='width:70%'></div>"
                     f"<div class='row'><span>{e(label)}</span><span class='big'>{e(big)}</span></div></div></div>")
    page.evaluate("() => document.fonts.ready")
    # 카드 폭에 맞춰 글자를 줄인다. 52px 밑으로 내려가야 들어가면 문구가 긴 것이다
    small = page.evaluate("""() => { const bad = [];
        for (const [sel, min] of [['.l1', 52], ['.l2', 40]]) { const el = document.querySelector(sel);
            let fs = parseFloat(getComputedStyle(el).fontSize);
            while (el.scrollWidth > el.clientWidth && fs > min) { fs -= 2; el.style.fontSize = fs + 'px'; }
            if (el.scrollWidth > el.clientWidth) bad.push(sel); }
        // 목업이 카드 글자를 가리면 안 된다(첫 견본에서 아랫줄 절반을 덮었다)
        const m = document.querySelector('.mock').getBoundingClientRect(), r = document.createRange();
        for (const sel of ['.l1', '.l2']) { r.selectNodeContents(document.querySelector(sel));
            for (const q of r.getClientRects()) if (q.bottom > m.top && q.top < m.bottom && q.right > m.left && q.left < m.right)
                { bad.push(sel + ' 겹침'); break; } }
        return bad; }""")
    page.wait_for_timeout(300)
    page.query_selector(".t").screenshot(path=str(out))
    font_ok = page.evaluate("() => document.fonts.check('52px Thumb')")
    problems = (["폰트가 적용되지 않았다"] if not font_ok else []) + \
               [f"{'윗줄' if s.startswith('.l1') else '아랫줄'}이 " + ("서류 목업에 가려진다" if "겹침" in s else "카드 폭을 넘는다 — 문구를 줄인다")
                for s in small]
    for x in problems:
        print(f"  ⚠ 썸네일(card): {x}  [{line1} | {line2}]")
    return not problems


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
    "11_실업급여_신청3단계": card_html("""
      <h2>실업급여 신청은 세 단계뿐</h2>
      <p class='sub'>앞의 둘을 끝내야 센터에서 접수된다</p>
      <div class='row'><span class='tag'>1단계</span><span class='txt'>워크넷 구직등록 — 구직신청 버튼까지 눌러야 인정</span><span class='num'>집에서</span></div>
      <div class='row'><span class='tag'>2단계</span><span class='txt'>수급자격 온라인 교육 — 1시간 안팎</span><span class='num'>집에서</span></div>
      <div class='row'><span class='tag'>3단계</span><span class='txt'>수급자격 신청 — 이 날이 모든 날짜의 기준</span><span class='num'>센터에서</span></div>
      <p class='foot'>이직확인서는 회사 몫입니다. 안 나왔다고 3단계를 미룰 필요는 없습니다.</p>
    """),
    "12_실업급여_첫입금": card_html("""
      <h2>첫 입금까지 걸리는 시간</h2>
      <p class='sub'>수급자격 신청일을 0일로 놓고</p>
      <div class='row'><span class='tag'>0일</span><span class='txt'>고용센터 방문, 수급자격 신청</span><span class='num'>기준일</span></div>
      <div class='row'><span class='tag'>+7일</span><span class='txt'>대기기간 — 이 기간은 지급되지 않음</span><span class='num'>0원</span></div>
      <div class='row'><span class='tag'>+14일</span><span class='txt'>1차 실업인정일</span><span class='num'>8일분</span></div>
      <div class='row'><span class='tag'>3주 안팎</span><span class='txt'>첫 입금, 상한액 기준</span><span class='num'>544,800원</span></div>
      <p class='foot'>첫 달은 한 달치가 아닙니다. 두 번째 회차부터 4주 단위로 커집니다.</p>
    """),
    "13_실업급여계산_공식": card_html("""
      <h2>구직급여, 계산기는 이렇게 돌아갑니다</h2>
      <p class='sub'>이직 전 3개월 평균임금 → 60% → 상하한 조정, 세 단계뿐</p>
      <div class='flow'>
        <div class='step'><div class='k'>STEP 1</div><div class='v'>3개월 총급여<br>÷ 91일</div><div class='d'>평균임금일액</div></div>
        <div class='arrow'>→</div>
        <div class='step'><div class='k'>STEP 2</div><div class='v'>× 60%</div><div class='d'>구직급여 기본값</div></div>
        <div class='arrow'>→</div>
        <div class='step'><div class='k'>STEP 3</div><div class='v'>상·하한<br>사이로 조정</div><div class='d'>최종 하루 금액</div></div>
      </div>
      <div class='range'>
        <div class='pill' style='background:#4263eb;'><div class='t'>이보다 낮으면 올림</div><div class='n'>하한 66,048원</div></div>
        <div class='gap'>차이<br><b>2,052원</b></div>
        <div class='pill' style='background:#f76707;'><div class='t'>이보다 높으면 내림</div><div class='n'>상한 68,100원</div></div>
      </div>
      <p class='foot'>하한은 2026년 최저임금 10,320원 × 80% × 8시간으로 정해집니다.</p>
    """),
    "14_실업급여계산_예시표": card_html("""
      <h2>월급별로 어디에 걸리는지</h2>
      <p class='sub'>같은 공식, 다른 결과 · 세 가지 월급으로 계산</p>
      <div class='exgrid'>
        <div class='ex'>
          <span class='badge' style='background:#4263eb;'>하한 적용</span>
          <div class='pay'>월 300만 원</div>
          <div class='amt'>66,048원 / 일</div>
          <div class='note'>60% 계산값 59,341원이<br>하한보다 낮아 올림</div>
        </div>
        <div class='ex'>
          <span class='badge' style='background:#12b886;'>그대로 적용</span>
          <div class='pay'>월 340만 원</div>
          <div class='amt'>67,253원 / 일</div>
          <div class='note'>상·하한 사이라<br>계산값 그대로</div>
        </div>
        <div class='ex'>
          <span class='badge' style='background:#f76707;'>상한 적용</span>
          <div class='pay'>월 500만 원</div>
          <div class='amt'>68,100원 / 일</div>
          <div class='note'>60% 계산값 98,901원이<br>상한보다 높아 내림</div>
        </div>
      </div>
      <p class='foot'>300만 원 × 180일 = 11,888,640원. 같은 월급도 가입기간에 따라 수백만 원 차이 납니다.</p>
    """),
    "15_국민연금_수령나이표": card_html("""
      <h2>출생연도별 국민연금 수령나이</h2>
      <p class='sub'>노령연금 지급개시연령 · 국민연금법 제61조</p>
      <div class='row'><span class='tag'>~1952년생</span><span class='txt'>60세부터</span></div>
      <div class='row'><span class='tag'>1953~56년생</span><span class='txt'>61세부터</span></div>
      <div class='row'><span class='tag'>1957~60년생</span><span class='txt'>62세부터</span></div>
      <div class='row'><span class='tag'>1961~64년생</span><span class='txt'>63세부터</span></div>
      <div class='row'><span class='tag'>1965~68년생</span><span class='txt'>64세부터</span></div>
      <div class='row'><span class='tag'>1969년생~</span><span class='txt'>65세부터</span></div>
      <p class='foot'>출생연도가 늦을수록 수령 나이가 1세씩 늦춰지도록 단계적으로 조정됩니다.</p>
    """),
    "16_국민연금_조기연기비교": card_html("""
      <h2>조기수령·연기수령, 5년 기준 얼마나 차이날까</h2>
      <p class='sub'>기본연금액 월 100만 원일 때 · 1년당 조기 6% 감액, 연기 7.2% 가산</p>
      <div class='exgrid'>
        <div class='ex'>
          <span class='badge' style='background:#e03131;'>5년 조기</span>
          <div class='pay'>30% 감액</div>
          <div class='amt'>70만 원</div>
          <div class='note'>당겨 받는 대신<br>평생 감액 적용</div>
        </div>
        <div class='ex'>
          <span class='badge' style='background:#495057;'>정상 수령</span>
          <div class='pay'>기준 금액</div>
          <div class='amt'>100만 원</div>
          <div class='note'>출생연도별<br>수령나이 도달 시</div>
        </div>
        <div class='ex'>
          <span class='badge' style='background:#1b64da;'>5년 연기</span>
          <div class='pay'>36% 가산</div>
          <div class='amt'>136만 원</div>
          <div class='note'>늦게 받는 대신<br>평생 가산 적용</div>
        </div>
      </div>
      <p class='foot'>한 번 정해진 감액·가산율은 평생 유지되고, 취소나 재조정은 되지 않습니다.</p>
    """),
    "17_지역가입자_건보료계산흐름": card_html("""
      <h2>지역가입자 건강보험료, 이렇게 더합니다</h2>
      <p class='sub'>소득보험료 + 재산보험료 = 월 보험료</p>
      <div class='flow'>
        <div class='step'><div class='k'>소득</div><div class='v'>연소득<br>× 7.19%</div><div class='d'>소득보험료</div></div>
        <div class='arrow'>+</div>
        <div class='step'><div class='k'>재산</div><div class='v'>재산 점수<br>× 211.5원</div><div class='d'>재산보험료</div></div>
        <div class='arrow'>=</div>
        <div class='step'><div class='k'>합산</div><div class='v'>월<br>보험료</div><div class='d'>최저 20,160원</div></div>
      </div>
      <p class='foot'>재산은 기본공제 1억 원을 뺀 금액부터 점수가 매겨지고, 자동차는 2024년 2월부터 빠졌습니다.</p>
    """),
    "18_직장가입자_지역가입자_비교": card_html("""
      <h2>직장가입자 vs 지역가입자, 계산이 다릅니다</h2>
      <p class='sub'>보는 항목 자체가 다르다</p>
      <div class='row'><span class='tag'>직장가입자</span><span class='txt'>보수월액 × 보험료율, 회사와 절반씩</span></div>
      <div class='row'><span class='tag'>지역가입자</span><span class='txt'>소득보험료 + 재산보험료, 전액 본인 부담</span></div>
      <p class='foot'>소득만 보던 직장가입자에서 은퇴 등으로 전환되면, 집이 있다는 이유로 보험료가 늘어날 수 있습니다.</p>
    """),
    "19_근로장려금_기한후_감액": card_html("""
      <h2>기한후 신청하면 10% 깎입니다</h2>
      <p class='sub'>가구 유형별 최대액 기준 · 신청은 11월 30일까지</p>
      <div class='exgrid'>
        <div class='ex'>
          <span class='badge' style='background:#1b64da;'>단독</span>
          <div class='pay'>165만 원 →</div>
          <div class='amt'>148.5만 원</div>
          <div class='note'>15만 원 5천 원 감액</div>
        </div>
        <div class='ex'>
          <span class='badge' style='background:#12b886;'>홑벌이</span>
          <div class='pay'>285만 원 →</div>
          <div class='amt'>256.5만 원</div>
          <div class='note'>28만 5천 원 감액</div>
        </div>
        <div class='ex'>
          <span class='badge' style='background:#f76707;'>맞벌이</span>
          <div class='pay'>330만 원 →</div>
          <div class='amt'>297만 원</div>
          <div class='note'>33만 원 감액</div>
        </div>
      </div>
      <p class='foot'>소득·재산 요건은 정기신청과 같습니다. 줄어드는 것은 지급액 10%뿐입니다.</p>
    """),
    "20_근로장려금_기한후_지급일정": card_html("""
      <h2>기한후 신청, 입금은 언제 되나</h2>
      <p class='sub'>신청한 달의 말일부터 4개월 이내 · 세무서 개별 심사</p>
      <div class='row'><span class='tag'>~11/30</span><span class='txt'>기한후 신청 마감 (12월 1일부터 접수 불가)</span></div>
      <div class='row'><span class='tag'>10월 신청</span><span class='txt'>10월 말부터 4개월 이내</span><span class='num'>2027년 2월 말까지</span></div>
      <div class='row'><span class='tag'>11월 신청</span><span class='txt'>11월 말부터 4개월 이내</span><span class='num'>2027년 3월 말까지</span></div>
      <p class='foot'>정기신청처럼 일괄 지급되지 않고 심사가 끝나는 순서대로 입금됩니다.</p>
    """),
    "21_납부확인서_자격득실확인서_비교": card_html("""
      <h2>납부확인서 vs 자격득실확인서</h2>
      <p class='sub'>이름은 비슷하지만 증명하는 내용이 다릅니다</p>
      <div class='row'><span class='tag'>납부확인서</span><span class='txt'>기간별로 보험료를 얼마 냈는지</span><span class='num'>금액</span></div>
      <div class='row'><span class='tag'>자격득실</span><span class='txt'>언제 가입하고 언제 빠졌는지</span><span class='num'>가입 이력</span></div>
      <p class='foot'>납부확인서는 2001년 이후 납부분부터 발급됩니다. 제출처가 어느 쪽을 원하는지 먼저 확인하세요.</p>
    """),
    "22_납부확인서_발급경로": card_html("""
      <h2>건강보험료 납부확인서 발급 경로 4가지</h2>
      <p class='sub'>국민건강보험공단 안내 기준</p>
      <div class='row'><span class='tag'>홈페이지</span><span class='txt'>로그인 → 개인민원 → 보험료 납부확인서</span></div>
      <div class='row'><span class='tag'>모바일 앱</span><span class='txt'>건강보험25시 (옛 The건강보험)</span></div>
      <div class='row'><span class='tag'>전화</span><span class='txt'>디지털ARS로 직접 신청</span><span class='num'>1577-1000</span></div>
      <div class='row'><span class='tag'>지사 방문</span><span class='txt'>신분증 지참</span></div>
      <p class='foot'>직장가입자의 피부양자는 보험료 납부 대상이 아니어서 발급되지 않습니다.</p>
    """),
    "23_납부확인서_발급화면_순서": card_html("""
      <h2>발급 화면에서 고르는 순서</h2>
      <p class='sub'>공단 홈페이지 기준 · 용도를 잘못 고르면 다시 발급해야 합니다</p>
      <div class='flow'>
        <div class='step'><div class='k'>1</div><div class='v'>발급<br>언어</div><div class='d'>국내 제출은 한글</div></div>
        <div class='arrow'>→</div>
        <div class='step'><div class='k'>2</div><div class='v'>기간</div><div class='d'>연월 정하고 조회</div></div>
        <div class='arrow'>→</div>
        <div class='step'><div class='k'>3</div><div class='v'>용도</div><div class='d'>제출처에 먼저 확인</div></div>
        <div class='arrow'>→</div>
        <div class='step'><div class='k'>4</div><div class='v'>보험<br>종류</div><div class='d'>건강보험 등</div></div>
      </div>
      <p class='foot'>고른 뒤 프린트 발급 또는 팩스전송을 누릅니다. 납부 직후에는 반영까지 영업일 2~3일이 걸립니다.</p>
    """),
    "24_실업급여_소정급여일수표": card_html("""
      <h2>실업급여 받는 일수, 가입기간과 나이로 정해집니다</h2>
      <p class='sub'>소정급여일수 · 고용보험법 별표 1 · 나이는 이직일 기준</p>
      <div class='row'><span class='tag'>1년 미만</span><span class='txt'>50세 미만 120일</span><span class='num'>50세 이상 120일</span></div>
      <div class='row'><span class='tag'>1~3년</span><span class='txt'>50세 미만 150일</span><span class='num'>50세 이상 180일</span></div>
      <div class='row'><span class='tag'>3~5년</span><span class='txt'>50세 미만 180일</span><span class='num'>50세 이상 210일</span></div>
      <div class='row'><span class='tag'>5~10년</span><span class='txt'>50세 미만 210일</span><span class='num'>50세 이상 240일</span></div>
      <div class='row'><span class='tag'>10년 이상</span><span class='txt'>50세 미만 240일</span><span class='num'>50세 이상 270일</span></div>
      <p class='foot'>장애인은 나이와 관계없이 50세 이상 기준을 적용합니다.</p>
    """),
    "25_실업급여_경계_하루차이": card_html("""
      <h2>경계를 하루 넘기면 달라지는 일수</h2>
      <p class='sub'>금액은 2026년 하한액 하루 66,048원 기준</p>
      <div class='exgrid'>
        <div class='ex'>
          <span class='badge' style='background:#1b64da;'>가입 1년 · 50세 미만</span>
          <div class='pay'>120일 →</div>
          <div class='amt'>150일</div>
          <div class='note'>+30일<br>약 198만 원</div>
        </div>
        <div class='ex'>
          <span class='badge' style='background:#12b886;'>가입 1년 · 50세 이상</span>
          <div class='pay'>120일 →</div>
          <div class='amt'>180일</div>
          <div class='note'>+60일<br>약 396만 원</div>
        </div>
        <div class='ex'>
          <span class='badge' style='background:#f76707;'>50세 생일 · 가입 1~3년</span>
          <div class='pay'>150일 →</div>
          <div class='amt'>180일</div>
          <div class='note'>+30일<br>약 198만 원</div>
        </div>
      </div>
      <p class='foot'>3년·5년·10년 경계에서도 30일씩 늘어납니다. 기준일은 퇴사한 날(이직일)입니다.</p>
    """),
    "26_실업급여_가입기간_합산": card_html("""
      <h2>이전 직장 가입기간, 합쳐지는 경우와 아닌 경우</h2>
      <p class='sub'>고용보험법 제50조</p>
      <div class='row'><span class='tag'>합산</span><span class='txt'>이전 직장 상실일부터 3년 안에 다시 가입</span></div>
      <div class='row'><span class='tag'>제외</span><span class='txt'>이전 직장을 나오며 실업급여를 받은 기간</span></div>
      <div class='row'><span class='tag'>제외</span><span class='txt'>상실 후 3년을 넘겨 다시 가입한 경우의 이전 기간</span></div>
      <p class='foot'>지금 회사 근속만이 아니라 합산된 가입기간으로 일수가 정해집니다.</p>
    """),
    "27_실업급여_해외여행_기준": card_html("""
      <h2>실업급여 받는 중 해외여행, 기준은 세 가지</h2>
      <p class='sub'>고용노동부 고객상담센터 안내 기준</p>
      <div class='row'><span class='tag'>여행</span><span class='txt'>출국·해외여행 자체는 제한 없음</span><span class='num'>가능</span></div>
      <div class='row'><span class='tag'>실업인정일</span><span class='txt'>그날은 국내에서 본인이 직접 신청</span><span class='num'>필수</span></div>
      <div class='row'><span class='tag'>해외 접속</span><span class='txt'>해외에서 인터넷으로 신청하면 부정수급</span><span class='num'>환수</span></div>
      <p class='foot'>여행 기간이 2주든 한 달이든, 따지는 것은 실업인정일과 겹치는지입니다.</p>
    """),
    "28_실업급여_실업인정일_날짜변경": card_html("""
      <h2>여행과 실업인정일이 겹칠 때</h2>
      <p class='sub'>실업인정일 변경 · 고용보험법 시행규칙</p>
      <div class='row'><span class='tag'>출국 전</span><span class='txt'>고용센터에 실업인정일 변경이 되는지 문의</span></div>
      <div class='row'><span class='tag'>놓쳤다면</span><span class='txt'>실업인정일 다음 날부터 고용센터 출석</span><span class='num'>14일 이내</span></div>
      <div class='row'><span class='tag'>착오 사유</span><span class='txt'>날짜를 잊은 경우의 변경</span><span class='num'>수급기간 중 1회</span></div>
      <p class='foot'>해외 취업이 목적이면 출국 전 해외 재취업활동계획서를 내고 해외에서 인정받는 길이 따로 있습니다.</p>
    """),
    "29_연말정산_부양가족_150만원": hero_card(
        ACCENT["세금"], "부양가족 한 명마다 빠지는 소득", "기본공제 · 2026년 귀속 연말정산",
        "150", "만 원", "나이 요건과 소득 요건을 둘 다 채운 가족 한 명당 소득에서 150만 원을 뺍니다.",
        "장애인은 나이 요건이 없고 200만 원이 더 공제됩니다."),
    "30_연말정산_부양가족_개편안_시점": timeline_card(
        ACCENT["세금"], "소득 기준 300만 원, 언제부터인가", "2026년 세제개편안 · 국회 통과 전",
        [("2026년 8월 3일", "정부가 세제개편안 발표", "소득금액 100만 원 → 300만 원, 총급여 500만 원 → 750만 원"),
         ("2027년 1~2월", "이번 연말정산 (2026년 소득분)", "지금 기준 그대로 100만 원 · 500만 원"),
         ("2027년 1월 1일 이후", "개편안이 적용되는 소득", "국회를 통과해야 확정됩니다"),
         ("2028년 초", "새 기준으로 하는 첫 연말정산", "2027년 소득분부터")],
        "100만 원 기준은 1996년부터, 총급여 500만 원 기준은 2016년부터 유지돼 왔습니다."),
    "31_연말정산_부양가족_실수": checklist_card(
        ACCENT["세금"], "부양가족을 올리기 전에 확인할 것", "국세청이 안내한 자주 틀리는 유형",
        [("가족의 소득금액이 100만 원 이하인가", "근로소득만 있으면 총급여 500만 원 이하"),
         ("집이나 상가를 판 해가 아닌가", "양도소득금액도 소득 기준에 들어갑니다"),
         ("형제자매와 부모님을 겹쳐 올리지 않았는가", "같은 부모님은 한 명만 공제받습니다"),
         ("소득 초과 가족의 카드·보험료를 넣지 않았는가", "의료비만 소득 요건 없이 공제됩니다")],
        "과다공제로 점검받으면 덜 낸 세금에 가산세가 붙습니다."),
    "32_연말정산_월세_공제액": bar_card(
        ACCENT["세금"], "월세에 따라 줄어드는 세금", "총급여 5,500만 원 이하 · 공제율 17% · 2026년 귀속",
        [("월세 40만 원 (연 480만 원)", "81만 6천 원", 48), ("월세 60만 원 (연 720만 원)", "122만 4천 원", 72),
         ("월세 100만 원 (한도 1,000만 원 적용)", "170만 원", 100)],
        "총급여 5,500만 원 초과 8,000만 원 이하는 15%, 최대 150만 원입니다."),
    "33_연말정산_월세_조건": checklist_card(
        ACCENT["세금"], "월세 세액공제를 받는 조건", "국세청 연말정산 안내 · 2026년 귀속",
        [("12월 31일 기준 무주택 세대인가", "세대주가 공제받지 않으면 세대원도 가능합니다"),
         ("총급여가 8,000만 원 이하인가", "종합소득금액으로는 7,000만 원 이하"),
         ("전용 85㎡ 이하이거나 기준시가 4억 원 이하인가", "주거용 오피스텔과 고시원도 포함됩니다"),
         ("계약서 주소로 전입신고를 했는가", "주민등록등본 주소와 계약서 주소가 같아야 합니다")],
        "확정일자는 요건이 아닙니다."),
    "34_연말정산_중도퇴사_순서": timeline_card(
        post_look(14), "2026년에 퇴사했다면 이 순서로", "소득세법 제137조·제138조·제143조",
        [("퇴사하는 달", "회사가 그날까지의 급여로 먼저 정산", "공제신고서를 안 냈다면 본인 기본공제와 표준세액공제 13만 원만"),
         ("다음 달 말일까지", "근로소득 원천징수영수증 받기", "전 회사가 발급합니다"),
         ("2027년 1~2월", "같은 해에 재취업했다면", "새 회사에 영수증을 내고 합산해 연말정산"),
         ("2027년 5월", "재취업하지 않았다면", "홈택스에서 종합소득세 신고로 빠진 공제 넣기")],
        "영수증의 결정세액에 금액이 있어야 더 돌려받을 세금이 있습니다."),
    "35_연말정산_의료비_문턱": hero_card(
        post_look(15), "의료비는 여기서부터 공제됩니다", "국세청 특별세액공제 안내 · 2026년 귀속",
        "3", "% 초과", "총급여의 3%를 넘긴 의료비에만 15%를 공제합니다. 총급여 5,000만원이면 150만원까지는 공제되지 않습니다.",
        "실손보험으로 돌려받은 금액은 의료비에서 먼저 뺍니다."),
    "36_연말정산_의료비_부부": bar_card(
        post_look(15), "병원비 300만원, 낸 사람에 따라", "의료비 15% · 실손보험금 없음 가정",
        [("총급여 6,000만원인 사람이 냄 (문턱 180만원)", "18만원", 57), ("총급여 3,000만원인 사람이 냄 (문턱 90만원)", "31만 5천원", 100)],
        "줄어드는 세금은 그 사람이 낼 세금(결정세액)보다 클 수 없습니다."),
    "37_건강보험료_환급금_3년": hero_card(
        post_look(16), "환급금을 받을 수 있는 기간", "국민건강보험법 제91조(시효)",
        "3", "년", "보험료 과오납, 상한액 초과, 과다 본인부담금 모두 3년 동안 신청하지 않으면 받을 권리가 사라집니다.",
        "조회는 공단 홈페이지·건강보험25시 앱·1577-1000에서 합니다."),
    "38_건강보험료_환급금_정산": timeline_card(
        post_look(16), "여러 병원 병원비가 상한액을 넘었다면", "국민건강보험공단 본인부담상한제 안내",
        [("2026년 1~12월", "진료받고 병원비 내기", "비급여·상급병실(2~3인실) 입원료 등은 합산에서 빠집니다"),
         ("2027년 8월경", "공단이 상한액과 초과금 확정", "연평균 건강보험료로 소득 구간을 정합니다"),
         ("확정 뒤", "지급신청서가 든 안내문 받기", "홈페이지·앱·전화·지사·팩스·우편으로 신청"),
         ("3년 안", "신청해야 받을 수 있음", "국민건강보험법 제91조")],
        "한 병원에서 843만원을 넘긴 몫은 병원 창구에서 바로 빠집니다(사전급여)."),
    "39_노령연금_10년": hero_card(
        post_look(17), "노령연금을 받는 기준은 하나", "국민연금법 제61조",
        "10", "년 이상", "국민연금 가입기간이 10년 이상이면 노령연금을 평생 매달 받습니다. 자동차나 재산은 보지 않습니다.",
        "10년 미만이면 낸 보험료에 이자를 더해 반환일시금으로 받습니다."),
    "40_노령연금_기간채우기": checklist_card(
        post_look(17), "10년이 모자랄 때 확인할 것", "국민연금법 제13조·제78조·제92조",
        [("보험료를 못 낸 기간이 있는가", "추후납부 — 10년 미만의 범위에서 신청"),
         ("반환일시금을 받은 적이 있는가", "반납하면 그 기간을 다시 가입기간으로 셉니다"),
         ("60세가 지났는가", "65세까지 임의계속가입을 신청할 수 있습니다")],
        "내 가입 이력은 국민연금공단에서 확인합니다."),
}

# 34번(14편)부터는 글 색 + 글자 1.5배다. ACCENT를 습관대로 쓰면 작은 글자·다른 색 카드가 조용히 나온다.
_old_look = [k for k in CARDS if int(k[:2]) >= 34 and f"zoom:{CARD_ZOOM}" not in CARDS[k]]
assert not _old_look, f"post_look(편 번호)를 쓰지 않은 카드: {_old_look}"


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


def shoot_cards(page, cards=None, out=None) -> list:
    broken = []
    cards, out = cards or CARDS, out or OUT
    for name, html in cards.items():
        page.set_viewport_size({"width": W, "height": 700})
        page.set_content(html)
        page.wait_for_timeout(400)
        over = find_overflow(page)
        el = page.query_selector(".card")
        el.screenshot(path=str(out / f"{name}.png"))
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


# 새 형태 4종의 견본. 발행용이 아니라 모양을 확인하는 용도라 _workspace에 만든다.
SAMPLES = {
    "견본_큰숫자": hero_card(ACCENT["실업급여"], "실업인정일을 놓쳤다면", "고용노동부 고객상담센터 안내 기준",
                        "14", "일 이내", "실업인정일 다음 날부터 세고, 고용센터에 직접 출석해야 합니다.",
                        "착오로 날짜를 잊은 경우의 변경은 수급기간 중 1회만 인정됩니다."),
    "견본_막대비교": bar_card(ACCENT["실업급여"], "가입기간이 길수록 받는 일수가 늘어납니다", "50세 미만 · 고용보험법 별표 1",
                        [("1년 미만", "120일", 44), ("1~3년", "150일", 56), ("3~5년", "180일", 67),
                         ("5~10년", "210일", 78), ("10년 이상", "240일", 89)],
                        "막대 길이는 최대 270일(50세 이상·10년 이상) 대비 비율입니다."),
    "견본_타임라인": timeline_card(ACCENT["근로장려금"], "기한후 신청부터 입금까지", "신청한 달의 말일부터 4개월 이내",
                            [("~11월 30일", "기한후 신청 마감", "12월 1일부터는 접수 자체가 닫힙니다"),
                             ("신청 후", "세무서 개별 심사", "정기신청처럼 일괄 지급되지 않습니다"),
                             ("10월 신청 → 2027년 2월 말", "입금", "11월 신청이면 2027년 3월 말까지")],
                            "지급액은 정기신청보다 10% 적습니다."),
    "견본_체크리스트": checklist_card(ACCENT["실업급여"], "출국 전에 확인할 것", "실업급여 받는 중 해외여행",
                              [("여행 기간에 실업인정일이 들어 있는가", "겹치지 않으면 따로 할 일이 없습니다"),
                               ("겹친다면 고용센터에 날짜 변경을 문의했는가", "개인 여행이 변경 사유가 되는지는 고용센터가 판단합니다"),
                               ("그 기간의 구직활동을 채웠는가", "못 채우면 그 회차는 인정받지 못합니다"),
                               ("해외에서 접속해 신청하지 않기로 했는가", "해외에서 인터넷으로 신청하면 부정수급입니다")],
                              "실업인정일 당일에는 국내에서 본인이 직접 신청해야 합니다."),
}


def find_cover(num: str):
    """표지 원본은 편마다 하나여야 한다. 15편에서 card용 cover_15.jpg가 남아 있어 AI 그림 cover_15.png 대신 사진을 집을 뻔했다."""
    ws = Path(__file__).parent / "_workspace" / "naver"
    found = [p for ext in ("jpg", "jpeg", "png", "webp") for p in ws.glob(f"cover_{num}.{ext}")]
    if len(found) > 1:
        raise SystemExit(f"표지 원본이 {len(found)}개다 — 쓸 것 하나만 남기고 이름을 바꾸세요: {', '.join(p.name for p in found)}")
    return found[0] if found else None


def unreferenced(names) -> list:
    """원고 어디에도 `이름.png`가 없는 카드. 17편에서 40번 카드를 만들어 놓고 원고에 자리를 안 만들었다(2026-10-16)."""
    text = "".join(p.read_text(encoding="utf-8") for p in (Path(__file__).parent / "content" / "naver").glob("[0-9][0-9]_*.md"))
    return [n for n in names if f"{n}.png" not in text]


def draft_md(num: str):
    drafts = list((Path(__file__).parent / "content" / "naver").glob(f"{num}_*.md"))
    return drafts[0].read_text(encoding="utf-8") if drafts else ""


def scene_md(num: str):
    md = draft_md(num)
    if memo_value(md, "썸네일 유형") != "scene" or not memo_value(md, "썸네일 장면") or not thumb_text(md):
        print(f"{num}편 작성 메모에 `- 썸네일 유형: scene`, `- 썸네일 장면:`, `- 썸네일 문구:` 줄이 모두 있어야 합니다")
        return None
    return md


def prompt_cmd(num: str) -> int:
    """scene 썸네일 프롬프트를 낸다(앱에서 손으로 만들 때). 장면·문구는 원고 작성 메모에서 읽는다."""
    md = scene_md(num)
    if not md:
        return 1
    print(scene_prompt(md, int(num)))
    print(f"\n→ 만든 그림을 _workspace/naver/cover_{num}.png로 저장하고 `--thumb {num}`")
    return 0


# 2026-10-14 모델 시험(NAVER_GUIDE 「썸네일 모델 결정」): 문구 3개 × 4장에서 두 줄이 모두 정확한 비율이 100%였고
# 1장 실측 비용이 후보 중 가장 낮았다(출력 토큰 × $30/1M). 가격이 바뀌면 GEN_COST만 고친다.
GEN_MODEL, GEN_QUALITY, GEN_N = "gpt-image-2.5-flare", "medium", 4
GEN_COST = 0.0132       # 달러, 1024×1024 medium 1장


def gen_cmd(num: str) -> int:
    """scene 썸네일 후보 GEN_N장을 만든다 → _workspace/naver/cover_NN_1~4.png. 고르는 것은 사람이 한다(글자 확인)."""
    import base64
    import os

    import requests
    from dotenv import load_dotenv
    md = scene_md(num)
    if not md:
        return 1
    load_dotenv(Path(__file__).parent / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        print(".env에 OPENAI_API_KEY가 없습니다")
        return 1
    print(f"{GEN_MODEL} {GEN_QUALITY} {GEN_N}장 생성 — 예상 비용 약 ${GEN_N * GEN_COST:.2f}")
    r = requests.post("https://api.openai.com/v1/images/generations",
                      headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                      json={"model": GEN_MODEL, "prompt": scene_prompt(md, int(num)), "size": "1024x1024",
                            "quality": GEN_QUALITY, "n": GEN_N}, timeout=300)
    if not r.ok:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    data = r.json().get("data") or []
    if not data:
        raise RuntimeError(f"OpenAI 응답에 이미지가 없다: {r.text[:300]}")
    ws = Path(__file__).parent / "_workspace" / "naver"
    for i, d in enumerate(data, 1):
        (ws / f"cover_{num}_{i}.png").write_bytes(base64.b64decode(d["b64_json"]))
        print(ws / f"cover_{num}_{i}.png")
    if len(data) < GEN_N:
        print(f"⚠ {GEN_N}장을 요청했는데 {len(data)}장만 왔다")
    tokens = r.json().get("usage", {}).get("output_tokens")
    if tokens:
        print(f"실제 비용 약 ${tokens * 30 / 1e6:.3f}")
    print(f"\n→ 그림 속 글자가 `{' / '.join(thumb_text(md))}`와 같은 것을 골라 cover_{num}.png로 복사한 뒤 `--thumb {num}`")
    return 0


def thumb_cmd(num: str) -> int:
    md = draft_md(num)
    text, kind = thumb_text(md), memo_value(md, "썸네일 유형")
    photo = find_cover(num)
    if not text:
        print(f"{num}편 원고 작성 메모에 `- 썸네일 문구: 윗줄 | 아랫줄` 줄이 없습니다")
        return 1
    if not photo:
        print(f"{'Gemini 그림' if kind == 'scene' else '고른 대표 사진'}을 _workspace/naver/cover_{num}.jpg (또는 png·webp)로 저장한 뒤 다시 실행하세요")
        return 1
    out = OUT / f"{num}_썸네일.png"
    preview = Path(__file__).parent / "_workspace" / "naver" / f"{num}_썸네일_가로크롭.png"
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        page = b.new_page(device_scale_factor=2)
        if kind == "scene":
            shoot_thumb_scene(page, photo, out)
            ok = True
            print(f"  그림 속 글자가 문구와 같은지 눈으로 확인하세요: {' / '.join(text)}")
        elif kind == "card":
            big, _, label = (memo_value(md, "썸네일 강조 숫자") or "").partition("|")
            ok = shoot_thumb_card(page, photo, *(t.replace("/", " ") for t in text), big.strip(), label.strip(), out)
        else:       # 14편까지: 사진 + 아래 띠
            ok = shoot_thumb(page, photo, *text, out, crop_preview=preview)
            print(f"가로로 잘렸을 때: {preview}")
        b.close()
    print(out)
    return 0 if ok else 1


if __name__ == "__main__":
    if "--samples" in sys.argv:
        dest = Path(__file__).parent / "_workspace" / "naver" / "card_samples"
        dest.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            page = b.new_page(device_scale_factor=2)
            bad = shoot_cards(page, SAMPLES, dest)
            photo = next(iter(sorted((Path(__file__).parent / "_workspace" / "naver").glob("cover_*.jpg"))), None)
            if photo:       # card 썸네일 견본 — 글자가 카드에 다 들어가야 한다
                bad += [] if shoot_thumb_card(page, photo, "국민연금 일찍 받으면", "6% 줄 수 있어요", "6%",
                                              "1년당 감액", dest / "썸네일_card.png") else ["썸네일_card"]
            else:
                print("  ⚠ _workspace/naver/cover_*.jpg가 없어 card 썸네일 견본을 건너뜀")
            b.close()
        print(dest)
        sys.exit(1 if bad else 0)
    elif "--gen" in sys.argv:
        sys.exit(gen_cmd(sys.argv[sys.argv.index("--gen") + 1]))
    elif "--prompt" in sys.argv:
        sys.exit(prompt_cmd(sys.argv[sys.argv.index("--prompt") + 1]))
    elif "--thumb" in sys.argv:
        sys.exit(thumb_cmd(sys.argv[sys.argv.index("--thumb") + 1]))
    elif "--selftest" in sys.argv:
        canva_selftest()
    elif "--canva-data" in sys.argv:
        import json
        try:
            print(json.dumps(canva_data(int(sys.argv[sys.argv.index("--canva-data") + 1])), ensure_ascii=False, indent=1))
        except ValueError as e:
            sys.exit(f"카드를 템플릿에 못 맞춤: {e}")
    elif "--card" in sys.argv:      # 이름 일부로 골라 그 카드만 다시 만든다
        key = sys.argv[sys.argv.index("--card") + 1]
        picked = {k: v for k, v in CARDS.items() if key in k}
        if not picked:
            sys.exit(f"'{key}'가 들어간 카드가 없습니다")
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            bad = shoot_cards(b.new_page(device_scale_factor=2), picked)
            b.close()
        missing = unreferenced(picked)
        for n in missing:
            print(f"  ⚠ {n}.png — 어느 원고에도 [이미지] 자리가 없다. 원고에 넣거나 카드를 지운다")
        sys.exit(1 if bad or missing else 0)
    elif len(sys.argv) > 1:
        # 인자 없이 돌리면 카드 전체를 다시 만든다. `--help`를 쳤다가 발행된 카드까지 전부 다시 그려졌다(2026-10-13).
        sys.exit("사용법: make_naver_images.py [--card 이름 | --canva-data NN | --gen NN | --thumb NN | --prompt NN | --samples | --selftest]  (인자 없음 = 전체 재생성)")
    else:
        main()
