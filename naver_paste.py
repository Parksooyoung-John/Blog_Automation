"""네이버 원고(.md) → 스마트에디터 붙여넣기용 .html.

브라우저에서 열어 [본문 복사]를 누르면 볼드가 살아 있는 본문이 클립보드에 들어간다.
전에는 마크다운 기호를 지운 .txt를 만들었는데, 텍스트 파일로는 서식을 옮길 수 없어서
원고의 **강조**가 붙여넣는 순간 전부 사라졌다(2026-10-07).

    python -X utf8 naver_paste.py content/naver/02_실업급여-조건.md
    python -X utf8 naver_paste.py --selftest
"""
import html
import json
import re
import sys
from pathlib import Path

from check_naver import BOX_RE, TEMPLATE_FROM, box_lines, is_box, is_table, split_sentences, table_rows

# 색과 박스 모양(2026-10-12). 벤치마킹한 글(blog.naver.com/sky09020/224426006669)의 라이브 HTML에서 에디터가
# 받아준 것으로 확인된 형태만 쓴다 — 셀 배경색, pt 단위의 면별 테두리, 글자 색.
# 그 블로그는 글마다 색을 바꾼다(최근 12편에서 실측). 우리도 편 번호로 돌려 쓴다 — 이웃한 글은 색이 다르다.
# (이름, 주 색, 연한 배경). 주의의 빨강과 헷갈리는 붉은 계열은 뺐다.
PALETTE = [("남색", "#1a5276", "#ebf5fb"), ("갈색", "#6e2c00", "#fbeee6"), ("초록", "#0b5345", "#e8f8f5"),
           ("보라", "#5b2c6f", "#f5eef8"), ("청록", "#006064", "#e0f7fa")]
LINE, WARN, GRAY = "#BFBFBF", "#c0392b", "#7f8c8d"


def tone_of(path) -> int:
    """원고 파일 이름의 편 번호 → PALETTE 순번. 번호가 없으면 0."""
    m = re.match(r"\d+", Path(path).name)
    return int(m.group()) % len(PALETTE) if m else 0


def _cell(bg="", border=f"border:1.0pt solid {LINE}") -> str:
    return f'style="{border};padding:6px 10px' + (f";background-color:{bg}" if bg else "") + '"'


def _left(color) -> str:
    return f"border-top:none;border-right:none;border-bottom:none;border-left:4.5pt solid {color}"


CELL, A_CELL = _cell(), _cell("", "border:none")      # 일반 셀, 질문 박스의 답 줄


def _tone(n: int) -> tuple:
    """→ (주 색, 표 머리글 셀, 첫 열 셀, 박스 종류별 (셀, 제목 색), 질문 줄 셀)"""
    _, main, tint = PALETTE[n % len(PALETTE)]
    box = {"요약": (_cell(tint, f"border:2.25pt solid {main}"), main),
           "안내": (_cell("#f8f9f9", _left(main)), main),
           "주의": (_cell("#fff0ee", _left(WARN)), WARN),
           "출처": (_cell("#f4f6f7", _left(GRAY)), GRAY)}
    return main, _cell(main), _cell(tint), box, _cell(tint, f"border:none;border-top:1.0pt solid {main}")
# 15편 라이브의 표는 전부 본문의 73%였다(에디터가 style 폭을 무시한 것으로 보인다). width 속성도 실어 보낸다 —
# 받아 주는지는 16편 발행으로 확인한다. 안 되면 verify_naver.py가 표 폭 경고를 낸다(2026-10-15).
TABLE = '<table width="100%" style="border-collapse:collapse;width:100%">'
BODY_PX = 15      # verify_naver.BODY_FONT와 같은 값(16은 폰에서 한두 글자 줄바꿈이 잦아 15로)
BODY_FONT = "나눔바른고딕"      # 라이브 글의 se-ff-nanumbarungothic
# 문단·표 셀·빈 줄 전부에 싣는다. 13편은 표 셀과 빈 줄에 크기가 없어 스팬 148개 중 37개가 에디터 기본값으로 들어갔다.
# 굵기도 싣는다. 18편을 지우고 다시 붙여넣었을 때 본문 전체가 굵게 들어갔다 — 지운 자리에 남은 맨 위 질문의 볼드를 이어받았다(2026-10-17).
SPAN = f'<span style="font-size:{BODY_PX}px;font-family:\'{BODY_FONT}\',NanumBarunGothic;font-weight:normal">'
BLANK = f"<p>{SPAN}<br></span></p>"


# 15편부터의 템플릿 서식은 사용자가 15편을 발행한 모양 그대로다(2026-10-15, 라이브 HTML에서 읽음).
# 맨 위 질문: 일반 글자 24·나눔명조·볼드·가운데·#222222. 처음엔 '소제목' 컴포넌트로 바꾸게 했는데 사용자는 일반 글자로 썼다.
HOOK_RE = re.compile(r'"[^"\n]{2,40}\?"')
HOOK = ('<p style="text-align:center"><span style="font-size:24px;font-family:\'나눔명조\',NanumMyeongjo;color:#222222">'
        '<b>{}</b></span></p>')
# 번호 소제목(## 1. …)과 Q&A 제목(## 🐷 …): 일반 글자 24·나눔명조·볼드·글 색. 인용구를 입히지 않고 이대로 들어간다.
BIG_HEAD_RE = re.compile(r"(\d+\. |🐷 )")
BIG_HEAD = ('<p><span style="font-size:24px;font-family:\'나눔명조\',NanumMyeongjo;color:{color}">'
            '<b>{text}</b></span></p>')
# 번호 소제목(섹션 1~5) 앞에만 가로 구분선(본문 폭 전체). Q&A 앞에는 넣지 않는다(2026-10-19 사용자 확정). 15~18편은 에디터에서 손으로 넣었다 — 2026-10-17 사용자 요청으로 붙여넣기에 싣는다.
# 에디터가 <hr>을 구분선 컴포넌트로 받는지는 18편 붙여넣기로 확인한다. 안 들어가면 체크리스트대로 손으로 넣는다.
HR = '<hr style="border:none;border-top:1px solid #cccccc;width:100%">'
# 본문·표·박스 크기: 14편까지 15(BODY_PX), 15편 16(사용자가 16으로 발행), 16편부터 19(2026-10-15 사용자 결정 — 벤치마크 본문도 19)
TEMPLATE_PX = 19
PX_BY_POST = {15: 16}
# '오늘 바로 할 살림 체크'·'오늘의 살림 정리': 15편에서 손으로 입힌 인용구(선) 느낌을 1칸 표로 낸다 —
# 왼쪽 글 색 굵은 선 + 연한 글 색 배경 + 24·명조·볼드. 붙여넣기로 바로 들어간다(2026-10-15).
BAND_HEADS = ("오늘 바로 할 살림 체크", "오늘의 살림 정리")
BAND_HEAD = ('<tr><td style="border-top:none;border-right:none;border-bottom:none;border-left:4.5pt solid {main};'
             'padding:6px 10px;background-color:{tint}"><p><span style="font-size:24px;font-family:\'나눔명조\','
             'NanumMyeongjo;color:{main}"><b>{text}</b></span></p></td></tr>')
# 근거 자료: 제목과 목록을 한 박스로(연한 글 색 배경 + 글 색 테두리). 원고는 `## 근거 자료` + 목록 그대로 쓴다.
SOURCE_RE = re.compile(r"^## 근거 자료[ \t]*\n\s*\n((?:- .*(?:\n|$))+)", re.M)


def _p(inner: str, color="") -> str:
    """본문 한 줄. 크기와 폰트는 늘 같고(verify_naver가 15·나눔바른고딕이 아닌 글자를 센다) 색만 바꾼다."""
    return "<p>" + (SPAN[:-2] + f';color:{color}">' if color else SPAN) + inner + "</span></p>"

# 해시태그 줄: '#실업급여 #실업급여조건 ...'. '## 소제목'과 헷갈리면 안 된다.
TAG_RE = re.compile(r"^#\S+(?: +#\S+)+$", re.M)

CHECKLIST = """■ PC에서 끝낸 뒤 임시저장 (서식은 PC 에디터에서만 붙는다 — 폰 붙여넣기는 글자만 들어간다, 2026-10-19)
· [소제목] 줄은 '인용구'(선) 스타일 적용 후 표시는 지우기 (앞뒤 빈 줄은 넣지 말 것)
· (15편~) 번호 소제목(섹션 1~5) 앞 가로 구분선이 들어갔는지 확인(18편~ 붙여넣기로 들어간다). 없으면 손으로. Q&A 앞에는 넣지 않는다. 살림 띠·근거 박스도 붙여넣기로 들어간다(16편~)
· (15편~) 표·박스가 본문보다 좁게 들어가면 본문 폭에 꽉 차게 늘린다 (15편은 전부 73%였다)
· [이미지] 자리에 PNG 넣기. 첫 이미지가 썸네일이 된다
· 붙여넣은 뒤 볼드와 줄바꿈이 그대로인지 한 번 훑어보기

■ 폰에서 해도 되는 것 (임시저장 글을 앱에서 열어서)
· [경험 한 줄] 두 곳 — 후보 중 하나만 남기고 [ ] 줄·▶ 줄·나머지 후보 지우기 (가장 중요)
· (15편~) 내부 링크 소개 문장은 인용구(말풍선)로
· [내부 링크] 소개 문장 하나만 남기고, 줄을 바꾼 뒤 주소 붙여넣기 → 카드 생성
             ⚠ 문장 중간에 붙여넣으면 문장이 카드 앞뒤로 쪼개진다
             ⚠ 앞 문장은 글마다 다르게 — 같은 문장을 반복하면 그게 패턴이 된다
· 태그 입력(26편까지 10개, 27편부터 3~5개) — 1편에서 빠뜨렸던 항목이다. 발행 설정 창에서 확인
· 발행 설정: 카테고리 / 주제 비즈니스·경제 / 전체공개 / 검색허용 체크"""

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>붙여넣기용 — {title}</title>
<style>
body{{font-family:'Malgun Gothic',system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#222;line-height:1.7}}
section{{border:1px solid #ddd;border-radius:10px;padding:14px 18px;margin:0 0 18px}}
h2{{font-size:14px;color:#666;margin:0 0 8px;font-weight:600}}
button{{float:right;padding:6px 14px;border:0;border-radius:6px;background:#03c75a;color:#fff;font-weight:700;cursor:pointer}}
#body p{{margin:0}} pre{{white-space:pre-wrap;font:inherit;font-size:13px;color:#555;margin:0}}
</style></head><body>
<section><button onclick="copyText('title',this)">제목 복사</button><h2>제목</h2><div id="title">{title}</div></section>
<section><button onclick="copyRich(this)">본문 복사</button><h2>본문 — 볼드 포함</h2><div id="body">
{body}
</div></section>
<section><button onclick="copyText('tags',this)">태그 복사</button><h2>태그 (하나씩 엔터로 입력 · 띄어쓰기 없이)</h2><div id="tags">{tags}</div></section>
<section><h2>발행 전 체크 (복사되지 않음)</h2><pre>{checklist}</pre></section>
<script>
const PLAIN = {plain};
function done(b) {{ const t = b.textContent; b.textContent = '복사됨'; setTimeout(() => b.textContent = t, 1200); }}
function copyText(id, b) {{ navigator.clipboard.writeText(document.getElementById(id).innerText).then(() => done(b)); }}
function copyRich(b) {{
  const item = new ClipboardItem({{
    'text/html': new Blob([document.getElementById('body').innerHTML], {{type: 'text/html'}}),
    'text/plain': new Blob([PLAIN], {{type: 'text/plain'}}) }});
  navigator.clipboard.write([item]).then(() => done(b));
}}
</script></body></html>
"""


# 후보를 품은 자리: `[경험 한 줄 ① | A안(사실): 문장 | B안(해당될 때만): 문장]`,
# `[내부 링크 | A안: 소개 문장 | B안: 소개 문장 | https://…]`. 전부 본문에 펼쳐 넣는다 —
# 사용자가 에디터에 붙인 뒤 하나만 남기고 지운다(2026-10-10). 전에는 후보가 채팅에만 있어 따로 옮겨 적어야 했다.
OPTIONS_RE = re.compile(r"\[(경험 한 줄|내부 링크)([^|\]]*)\|([^\]]+)\]")


def _options(m) -> str:
    kind, items = m.group(1), [x.strip() for x in m.group(3).split("|")]
    what = "문장" if kind == "경험 한 줄" else "소개 문장"
    lines = [f"[{kind}{m.group(2).rstrip()} — {what} 하나만 남기고 ▶ 줄과 나머지는 지우세요]"]
    for it in items:
        if it.startswith("http"):
            lines += ["▶ 아래 주소를 잘라내 남긴 문장 다음 줄에 다시 붙여넣으면 카드가 됩니다", it]
        else:
            label, _, sentence = it.partition(": ")
            lines += [f"▶ {label}", sentence]
    return "\n".join(lines)


def parts(md: str) -> tuple:
    """→ (제목, 본문 마크다운, 태그 줄). 본문은 소제목·목록 표기를 바꾸고 문장마다 줄을 나눈 상태다."""
    body = md.split("## 작성 메모")[0]
    title = re.search(r"^제목: (.+)$", body, re.M).group(1).strip()
    m = TAG_RE.search(body)
    tags = m.group(0).strip() if m else ""

    body = re.sub(r"^제목: .+$", "", body, flags=re.M)
    body = TAG_RE.sub("", body)
    body = re.sub(r"^-{3,}$", "", body, flags=re.M)
    body = SOURCE_RE.sub(lambda m: "> [출처] 근거 자료\n" + "".join(f"> {ln}\n" for ln in m.group(1).strip().split("\n")), body)
    body = re.sub(r"^#{2,} (.+)$", lambda m: ("[큰제목] " if BIG_HEAD_RE.match(m.group(1)) else
                                              "[띠제목] " if m.group(1).strip() in BAND_HEADS else "[소제목] ") + m.group(1),
                  body, flags=re.M)
    body = re.sub(r"^- ✔", "✔", body, flags=re.M)        # 살림 체크 줄은 ✔만(15편 발행 모양) — "· ✔"로 겹치지 않게
    body = re.sub(r"^(> ?)?- ", r"\1· ", body, flags=re.M)
    body = body.replace("`", "")
    body = OPTIONS_RE.sub(_options, body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    assert "##" not in body, "소제목 변환 실패"
    # 27편부터 태그 3~5개(check_naver.TAG_RANGE). 5개 이상으로 고정해 두었다가 태그 4개인 27편에서 멈췄다(2026-10-28)
    assert tags.startswith("#") and tags.count("#") >= 3, f"태그 추출 실패: {tags!r}"

    # 문장 하나마다 빈 줄을 둔다(2026-10-09 사용자 확정 — 11편에서 손으로 넣던 모양).
    # 문장 중간은 끊지 않는다. 플레이스홀더([이미지 …] 등)·목록·표는 덩어리째 둔다.
    blocks = []
    for blk in body.split("\n\n"):
        plain_para = not is_table(blk) and not re.match(r"(\[|· |\d+\. |>|※|🪙)", blk)
        blocks += split_sentences(blk) if plain_para else [blk]
    return title, "\n\n".join(blocks), tags


def _rich(text: str, color: str = "") -> str:
    """**볼드** → <b>. color를 주면 볼드 글자를 그 글의 테마색으로 낸다(2026-10-24 사용자 규칙: 본문 볼드는 글 색)."""
    sub = rf'<b><span style="color:{color}">\1</span></b>' if color else r"<b>\1</b>"
    return re.sub(r"\*\*(.+?)\*\*", sub, html.escape(text))


def convert(md: str) -> str:
    """일반 텍스트(볼드 없음) — 서식을 받지 못하는 곳에 붙일 때 쓰이는 쪽. 표는 `a — b` 줄로 낸다."""
    _, body, _ = parts(md)
    blocks = ["\n".join(" — ".join(r) for r in table_rows(b)) if is_table(b)
              else "\n".join(box_lines(b)) if is_box(b) else b for b in body.split("\n\n")]
    return "\n\n".join(blocks).replace("**", "")


def to_html(md: str, tone: int = 0, template: bool = False, px: int = TEMPLATE_PX) -> str:
    """template: 15편부터의 서식 — 본문·표·박스 px, 표 가운데 정렬, 살림 소제목 띠·근거 자료 박스."""
    title, body, tags = parts(md)
    MAIN, HEAD, FIRST, BOX, Q_CELL = _tone(tone)
    tint = PALETTE[tone % len(PALETTE)][2]
    if template:
        BOX = {**BOX, "출처": (_cell(tint, f"border:1.5pt solid {MAIN}"), MAIN)}
    paras = []
    for k, blk in enumerate(body.split("\n\n")):
        if k == 0 and HOOK_RE.fullmatch(blk):       # 15편~ 맨 위 질문
            paras.append(HOOK.format(html.escape(blk)))
        elif blk.startswith("[큰제목] "):
            text = blk[len("[큰제목] "):]
            paras.append((HR if text[0].isdigit() else "") + BIG_HEAD.format(color=MAIN, text=_rich(text)))
        elif blk.startswith("[띠제목] "):
            paras.append(TABLE + BAND_HEAD.format(main=MAIN, tint=tint, text=_rich(blk[len("[띠제목] "):])) + "</table>")
        elif is_table(blk):       # 에디터가 자기 표로 바꾸도록 테두리만 준다
            head, *rest = table_rows(blk)
            rows = ["<tr>" + "".join(f"<th {HEAD}>{_p('<b>' + _rich(c) + '</b>', '#ffffff')}</th>" for c in head) + "</tr>"]
            # 칸 전체가 볼드인 값은 강조색으로(답이 되는 숫자)
            rows += ["<tr>" + "".join(f"<td {CELL if i else FIRST}>"
                                      + _p(_rich(c, "" if re.fullmatch(r"\*\*[^*]+\*\*", c) else MAIN),
                                           MAIN if re.fullmatch(r"\*\*[^*]+\*\*", c) else "") + "</td>"
                                      for i, c in enumerate(r)) + "</tr>" for r in rest]
            tbl = TABLE + "".join(rows) + "</table>"
            paras.append(tbl.replace("<p>", '<p style="text-align:center">') if template else tbl)
        elif is_box(blk):       # 에디터에 박스가 없어 1칸 표로 낸다
            kind, (head, *rest) = BOX_RE.match(blk).group(1), box_lines(blk)
            if kind == "질문":
                rows = (f"<tr><td {Q_CELL}>{_p('<b>Q. ' + _rich(head) + '</b>', MAIN)}</td></tr><tr><td {A_CELL}>"
                        + "".join(_p(("" if i else "A. ") + _rich(x, MAIN)) for i, x in enumerate(rest)) + "</td></tr>")
            else:
                cell, color = BOX[kind]
                rest = [x.replace("· ", "✓ ", 1) if kind == "요약" else x for x in rest]
                rows = f"<tr><td {cell}>{_p('<b>' + _rich(head) + '</b>', color)}{''.join(_p(_rich(x, MAIN)) for x in rest)}</td></tr>"
            paras.append(TABLE + rows + "</table>")
        else:
            # 글자 크기와 폰트를 실어 보낸다 — 에디터 기본값이 바뀌어도 같은 모양으로 들어가게.
            # `※`로 시작하는 줄은 표·문단에 딸린 주석이다(기준 연도·예외).
            paras += [_p(_rich(line, "" if line.startswith("※") else MAIN), WARN if line.startswith("※") else "")
                      for line in blk.split("\n")]
        paras.append(BLANK)          # 덩어리 사이 빈 줄
    assert "**" not in "".join(paras), "닫히지 않은 볼드 표시가 남았다"
    out = "\n".join(paras[:-1])
    if template:      # ponytail: SPAN·BLANK에 박힌 15px를 통째로 바꾼다. 크기를 글마다 따로 고르게 되면 _p에 인자로 넘긴다
        out = out.replace(f"font-size:{BODY_PX}px", f"font-size:{px}px")
    return PAGE.format(title=html.escape(title), body=out, tags=html.escape(tags),
                       checklist=html.escape(CHECKLIST),
                       plain=json.dumps(convert(md), ensure_ascii=False).replace("</", "<\\/"))


def selftest():
    md = ("제목: 테스트 제목\n\n---\n\n도입부입니다. 보험료율은 **7.19%**입니다. A < B인 경우도 있습니다.\n\n"
          "[이미지 ②: `assets/x.png` — 제작 완료]\n\n## 첫 소제목\n\n- 항목 **강조**\n- 둘째 항목\n\n"
          "#태그하나 #태그둘 #태그셋 #태그넷 #태그다섯\n\n---\n\n## 작성 메모 (발행 시 삭제)\n\n- 메모\n")
    text = convert(md)
    assert "[소제목] 첫 소제목" in text
    assert "· 항목 강조" in text
    # 문장마다 빈 줄을 두되 소수점에서는 끊기지 않는다. 목록 줄은 붙어 있다
    assert "도입부입니다.\n\n보험료율은 7.19%입니다.\n\nA < B인 경우도 있습니다." in text, text
    assert "· 항목 강조\n· 둘째 항목" in text
    assert "[이미지 ②: assets/x.png — 제작 완료]" in text      # 플레이스홀더는 한 줄 그대로
    assert "메모" not in text and "#태그하나" not in text

    page = to_html(md)
    MAIN, HEAD, FIRST, BOX, Q_CELL = _tone(0)
    P, E = f"<p>{SPAN}", "</span></p>"      # 본문 줄은 글자 크기와 폰트를 달고 나간다
    B = lambda t: f'<b><span style="color:{MAIN}">{t}</span></b>'      # 본문 볼드는 글 색(2026-10-24)
    assert "font-size:15px" in SPAN and "나눔바른고딕" in SPAN
    assert f"{P}보험료율은 {B('7.19%')}입니다.{E}" in page
    assert f"{P}· 항목 {B('강조')}{E}" in page
    assert "A &lt; B인" in page
    assert B("7.19%") in to_html(md, 0) and B("7.19%") not in to_html(md, 1)       # 볼드 색은 글마다 따라 바뀐다
    assert "<b>7.19%</b>" not in page                                              # 색 없는 볼드가 남으면 안 된다                                 # 본문의 < 가 태그로 읽히면 안 된다
    assert '<div id="tags">#태그하나 #태그둘 #태그셋 #태그넷 #태그다섯</div>' in page
    assert "작성 메모" not in page and "- 메모" not in page
    assert f"{P}도입부입니다.{E}\n{BLANK}\n{P}보험료율은" in page          # 문장 사이 빈 줄
    assert f"{P}· 항목 {B('강조')}{E}\n{P}· 둘째 항목{E}" in page             # 목록은 붙어 있다

    tmd = md.replace("- 항목 **강조**\n- 둘째 항목", "| 가입기간 | 일수 |\n|---|---|\n| 1년 미만 | **120일** |")
    tpage, ttext = to_html(tmd), convert(tmd)
    assert "<table" in tpage and f"<th {HEAD}>{_p('<b>가입기간</b>', '#ffffff')}</th>" in tpage      # 표 셀도 크기·폰트를 단다
    assert "<p><br></p>" not in tpage                             # 크기 없는 빈 줄이 남으면 안 된다
    assert f"<td {FIRST}>{P}1년 미만{E}</td>" in tpage and f"background-color:{MAIN}" in HEAD      # 머리글·첫 열에 배경색
    assert f"<td {CELL}>{_p('<b>120일</b>', MAIN)}</td>" in tpage                                # 통째 볼드인 칸은 강조색
    assert 'font-size:15px' in _p("x", MAIN) and "나눔바른고딕" in _p("x", MAIN)                   # 색을 바꿔도 크기·폰트는 실린다
    assert "|---" not in tpage and "---|" not in tpage
    # 글마다 색이 다르다: 이웃한 편은 다른 색, 주의·출처 색은 그대로
    assert [tone_of(f"content/naver/{n}_x.md") for n in (14, 15, 16)] == [4, 0, 1] and tone_of("paste_test.md") == 0
    assert len({m for _, m, _ in PALETTE}) == len(PALETTE) and WARN not in {m for _, m, _ in PALETTE}
    t1 = to_html(tmd, 1)
    assert f"background-color:{PALETTE[1][1]}" in t1 and f"background-color:{PALETTE[0][1]}" not in t1
    assert _tone(1)[3]["주의"] == BOX["주의"] and _tone(1)[3]["요약"] != BOX["요약"]
    assert "가입기간 — 일수\n1년 미만 — 120일" in ttext, ttext

    # 후보를 품은 자리는 전부 펼쳐진다. 후보 문장은 표시 없이 한 줄씩이라 남긴 줄을 그대로 쓸 수 있다
    omd = md.replace("## 첫 소제목", "[경험 한 줄 ① | A안(사실): 직접 **확인**했어요. | B안(해당될 때만): 저도 그랬어요.]\n\n"
                     "[내부 링크 | A안: 조건은 이 글에 있어요. | B안: 먼저 이 글을 보세요. | https://blog.naver.com/x/1]\n\n## 첫 소제목")
    otext, opage = convert(omd), to_html(omd)
    assert ("[경험 한 줄 ① — 문장 하나만 남기고 ▶ 줄과 나머지는 지우세요]\n▶ A안(사실)\n직접 확인했어요.\n"
            "▶ B안(해당될 때만)\n저도 그랬어요.") in otext, otext
    assert "▶ B안\n먼저 이 글을 보세요.\n▶ 아래 주소를 잘라내" in otext and otext.count("https://blog.naver.com/x/1") == 1, otext
    assert f"{P}직접 {B('확인')}했어요.{E}\n{P}▶ B안(해당될 때만){E}" in opage
    assert "[경험 한 줄 ②]" in convert(md.replace("## 첫 소제목", "[경험 한 줄 ②]\n\n## 첫 소제목"))   # 후보 없는 옛 표기는 그대로

    # 박스: 문장으로 쪼개지 않고 배경색 1칸 표 하나로 나간다. 일반 텍스트에는 `>`와 종류 표지가 남지 않는다
    bmd = md.replace("## 첫 소제목", "> [요약] 한눈에 보기\n> - 한도는 **1,000만원**입니다. 예외도 있습니다.\n> - 둘째 줄\n\n## 첫 소제목")
    btext, bpage = convert(bmd), to_html(bmd)
    assert "한눈에 보기\n· 한도는 1,000만원입니다. 예외도 있습니다.\n· 둘째 줄" in btext and "[요약]" not in btext and ">" not in btext, btext
    assert (f'<td {BOX["요약"][0]}>{_p("<b>한눈에 보기</b>", MAIN)}{P}✓ 한도는 {B('1,000만원')}입니다. 예외도 있습니다.{E}'
            f'{P}✓ 둘째 줄{E}</td>') in bpage
    assert f"<title>붙여넣기용 — 테스트 제목</title>" in bpage              # 박스 제목이 글 제목을 덮어쓰면 안 된다
    qmd = md.replace("## 첫 소제목", "> [질문] 언제부터 되나요?\n> 2027년부터입니다.\n\n※ 기준은 2026년입니다. 예외가 있습니다.\n\n## 첫 소제목")
    qpage = to_html(qmd)
    assert f"<td {Q_CELL}>{_p('<b>Q. 언제부터 되나요?</b>', MAIN)}</td></tr><tr><td {A_CELL}>{P}A. 2027년부터입니다.{E}</td>" in qpage
    assert _p("※ 기준은 2026년입니다. 예외가 있습니다.", WARN) in qpage      # 주석 줄은 문장으로 쪼개지 않고 통째로 색을 단다
    assert "Q. 언제부터" not in convert(qmd) and "언제부터 되나요?\n2027년부터입니다." in convert(qmd)
    assert "&gt;" not in bpage.split('id="body">')[1].split("</section>")[0]

    # 15편~ 템플릿: 맨 위 질문은 가운데 볼드 한 줄, 살림 메모 줄은 문장으로 쪼개지 않고 본문 색 그대로
    hmd = md.replace("도입부입니다.", '"연말정산은 1월에 하는 거 아니에요?"\n\n도입부입니다.').replace(
        "## 첫 소제목", "🪙 살림 메모: 2026년 기준입니다. 예외가 있습니다.\n\n## 첫 소제목")
    hpage = to_html(hmd)
    assert HOOK.format("&quot;연말정산은 1월에 하는 거 아니에요?&quot;") in hpage, hpage[:900]
    assert _p("🪙 살림 메모: 2026년 기준입니다. 예외가 있습니다.") in hpage
    assert hpage.count('text-align:center') == 1
    assert HOOK.split("{")[0] not in to_html(md.replace("도입부입니다.", '도입부입니다.\n\n"중간에 있는 질문은요?"'))  # 맨 위만
    assert "font-size:24px" in HOOK and "나눔명조" in HOOK
    assert all("나눔명조" in h for h in (BIG_HEAD, BAND_HEAD)), "소제목 폰트는 나눔명조(2026-10-17 사용자 규칙)"

    # 15편 발행 모양: 번호 소제목·🐷 Q&A는 24·명조·글 색 글자로, 나머지 소제목은 인용구용 [소제목] 표시로
    gmd = tmd.replace("## 첫 소제목", "## 1. 첫 결론입니다\n\n## 오늘의 살림 정리\n\n## 🐷 새싹돼지 Q&A")
    gpage, gtext = to_html(gmd, 1, template=True), convert(gmd)
    main1 = PALETTE[1][1]
    assert HR + BIG_HEAD.format(color=main1, text="1. 첫 결론입니다") in gpage                     # 번호 소제목 앞 구분선
    assert HR + BIG_HEAD.format(color=main1, text="🐷 새싹돼지 Q&amp;A") not in gpage                # Q&A 앞에는 구분선 없음
    assert BIG_HEAD.format(color=main1, text="🐷 새싹돼지 Q&amp;A") in gpage
    gbody = gpage.split('id="body">')[1].split("</section>")[0]
    assert "[소제목]" not in gbody and "[큰제목]" not in gbody and "[띠제목]" not in gbody
    tint1 = PALETTE[1][2]
    assert BAND_HEAD.format(main=main1, tint=tint1, text="오늘의 살림 정리") in gbody              # 살림 소제목은 띠로
    assert f"font-size:{TEMPLATE_PX}px" in gbody and "font-size:15px" not in gbody                  # 본문·표·빈 줄 전부 19
    body_spans = re.findall(rf'<span style="font-size:{TEMPLATE_PX}px[^"]*">', gbody)
    assert body_spans and all("font-weight:normal" in s for s in body_spans), "본문 글자에 굵기가 없으면 에디터의 볼드를 이어받는다"
    assert "font-size:16px" in to_html(gmd, 1, template=True, px=16)                                  # 15편은 16으로 발행
    smd = gmd.replace("## 🐷 새싹돼지 Q&A", "## 🐷 새싹돼지 Q&A\n\n## 근거 자료\n\n- 국민건강보험법 제91조\n- 공단 안내")
    sbody = to_html(smd, 1, template=True).split('id="body">')[1].split("</section>")[0]
    assert f"border:1.5pt solid {main1}" in sbody and "<b>근거 자료</b>" in sbody and "· 국민건강보험법 제91조" in sbody
    assert "[소제목] 근거 자료" not in sbody                                                       # 제목과 목록이 한 박스
    cmd = gmd.replace("## 오늘의 살림 정리", "## 오늘 바로 할 살림 체크\n\n- ✔ 조회하기\n- ✔ 신청하기")
    assert "✔ 조회하기\n✔ 신청하기" in convert(cmd) and "· ✔" not in convert(cmd)
    data_tbl = next(t for t in gbody.split("<table")[1:] if "가입기간" in t)
    assert '<p style="text-align:center">' in data_tbl                                            # 표 칸은 가운데
    assert "font-size:15px" in to_html(gmd, 1) and 'text-align:center">' not in to_html(gmd, 1).split("<table")[1]  # 14편까지는 그대로
    assert "[큰제목] 1. 첫 결론입니다" in gtext
    pc, phone = CHECKLIST.split("■ 폰에서")                                                       # 체크리스트가 PC/폰으로 나뉘어 있어야 한다
    assert "[이미지]" in pc and "[경험 한 줄]" in phone and "3~5개" in phone
    fresh = with_freshness(CHECKLIST, "- 최신성 재확인: 2026-10-31 14:00 | q | s\n")
    assert "최신성 재확인 10-31 14:00" in fresh and with_freshness(CHECKLIST, "메모") == CHECKLIST
    assert parts(md.replace(" #태그넷 #태그다섯", ""))[2] == "#태그하나 #태그둘 #태그셋"        # 27편부터 태그 3개도 읽는다
    print("selftest ok")


def with_freshness(page: str, md: str) -> str:
    """체크리스트 맨 끝에 최신성 재확인 시각을 적는다. 파일을 만든 뒤 늦게 올리는 경우는 코드가 막지 못한다."""
    from check_naver import freshness_time
    t = freshness_time(md)
    return page.replace("· 발행 설정:", f"· 최신성 재확인 {t:%m-%d %H:%M} — 하루 지났으면 개통·기간·금액을 다시 확인\n· 발행 설정:") if t else page


def page_for(src: Path, tone: int = None) -> str:
    """원고 파일 → 붙여넣기 HTML. 편 번호로 템플릿 여부·글자 크기를 정한다.

    naver_prep.py가 to_html(md, tone)만 불러 18편 파일이 15px·템플릿 서식 없이 나왔다(2026-10-17).
    붙여넣기 파일을 만드는 곳은 전부 이 함수를 거친다."""
    num = re.match(r"\d+", src.name)
    if num:
        from pipeline import paste_gate      # 승인 흐름에 올라오지 않은 글은 붙여넣기 파일을 만들지 않는다(25편~)
        paste_gate(int(num.group()))
    template = bool(num) and int(num.group()) >= TEMPLATE_FROM
    px = PX_BY_POST.get(int(num.group()), TEMPLATE_PX) if num else TEMPLATE_PX
    md = src.read_text(encoding="utf-8")
    return with_freshness(to_html(md, tone_of(src) if tone is None else tone, template, px), md)


if __name__ == "__main__":
    if sys.argv[1] == "--selftest":
        selftest()
    else:
        src = Path(sys.argv[1])
        out = src.with_name(src.stem + "_붙여넣기용.html")
        tone = int(sys.argv[2]) if len(sys.argv) > 2 else tone_of(src)      # 둘째 인자로 색 순번을 직접 줄 수 있다
        out.write_text(page_for(src, tone), encoding="utf-8")
        print(out, "· 색:", PALETTE[tone % len(PALETTE)][0])
