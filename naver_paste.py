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

from check_naver import is_table, split_sentences, table_rows

CELL = 'style="border:1px solid #c8c8c8;padding:6px 10px"'
BODY_PX = 15      # verify_naver.BODY_FONT와 같은 값(16은 폰에서 한두 글자 줄바꿈이 잦아 15로)
BODY_FONT = "나눔바른고딕"      # 라이브 글의 se-ff-nanumbarungothic
# 문단·표 셀·빈 줄 전부에 싣는다. 13편은 표 셀과 빈 줄에 크기가 없어 스팬 148개 중 37개가 에디터 기본값으로 들어갔다.
SPAN = f'<span style="font-size:{BODY_PX}px;font-family:\'{BODY_FONT}\',NanumBarunGothic">'
BLANK = f"<p>{SPAN}<br></span></p>"

# 해시태그 줄: '#실업급여 #실업급여조건 ...'. '## 소제목'과 헷갈리면 안 된다.
TAG_RE = re.compile(r"^#\S+(?: +#\S+)+$", re.M)

CHECKLIST = """· 태그 10개 입력 — 1편에서 빠뜨렸던 항목이다. 발행 설정 창에서 확인
· [소제목] 줄은 '인용구' 스타일 적용 후 표시는 지우기 (앞뒤 빈 줄은 넣지 말 것)
· [이미지] 자리에 PNG 넣기. 첫 이미지가 썸네일이 된다
· [경험 한 줄] 두 곳 — 후보 중 하나만 남기고 [ ] 줄·▶ 줄·나머지 후보 지우기 (가장 중요)
· [내부 링크] 소개 문장 하나만 남기고, 줄을 바꾼 뒤 주소 붙여넣기 → 카드 생성
             ⚠ 문장 중간에 붙여넣으면 문장이 카드 앞뒤로 쪼개진다
             ⚠ 앞 문장은 글마다 다르게 — 같은 문장을 반복하면 그게 패턴이 된다
· 붙여넣은 뒤 볼드와 줄바꿈이 그대로인지 한 번 훑어보기
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
    body = re.sub(r"^#{2,} (.+)$", r"[소제목] \1", body, flags=re.M)
    body = re.sub(r"^- ", "· ", body, flags=re.M)
    body = body.replace("`", "")
    body = OPTIONS_RE.sub(_options, body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    assert "##" not in body, "소제목 변환 실패"
    assert tags.startswith("#") and tags.count("#") >= 5, f"태그 추출 실패: {tags!r}"

    # 문장 하나마다 빈 줄을 둔다(2026-10-09 사용자 확정 — 11편에서 손으로 넣던 모양).
    # 문장 중간은 끊지 않는다. 플레이스홀더([이미지 …] 등)·목록·표는 덩어리째 둔다.
    blocks = []
    for blk in body.split("\n\n"):
        plain_para = not is_table(blk) and not re.match(r"(\[|· |\d+\. )", blk)
        blocks += split_sentences(blk) if plain_para else [blk]
    return title, "\n\n".join(blocks), tags


def _rich(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


def convert(md: str) -> str:
    """일반 텍스트(볼드 없음) — 서식을 받지 못하는 곳에 붙일 때 쓰이는 쪽. 표는 `a — b` 줄로 낸다."""
    _, body, _ = parts(md)
    blocks = ["\n".join(" — ".join(r) for r in table_rows(b)) if is_table(b) else b for b in body.split("\n\n")]
    return "\n\n".join(blocks).replace("**", "")


def to_html(md: str) -> str:
    title, body, tags = parts(md)
    paras = []
    for blk in body.split("\n\n"):
        if is_table(blk):       # 에디터가 자기 표로 바꾸도록 테두리만 준다
            head, *rest = table_rows(blk)
            rows = ["<tr>" + "".join(f"<th {CELL}>{SPAN}{_rich(c)}</span></th>" for c in head) + "</tr>"]
            rows += ["<tr>" + "".join(f"<td {CELL}>{SPAN}{_rich(c)}</span></td>" for c in r) + "</tr>" for r in rest]
            paras.append('<table style="border-collapse:collapse">' + "".join(rows) + "</table>")
        else:
            # 글자 크기와 폰트를 실어 보낸다 — 에디터 기본값이 바뀌어도 같은 모양으로 들어가게.
            paras += [f"<p>{SPAN}" + _rich(line) + "</span></p>" for line in blk.split("\n")]
        paras.append(BLANK)          # 덩어리 사이 빈 줄
    assert "**" not in "".join(paras), "닫히지 않은 볼드 표시가 남았다"
    return PAGE.format(title=html.escape(title), body="\n".join(paras[:-1]), tags=html.escape(tags),
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
    P, E = f"<p>{SPAN}", "</span></p>"      # 본문 줄은 글자 크기와 폰트를 달고 나간다
    assert "font-size:15px" in SPAN and "나눔바른고딕" in SPAN
    assert f"{P}보험료율은 <b>7.19%</b>입니다.{E}" in page
    assert f"{P}· 항목 <b>강조</b>{E}" in page
    assert "A &lt; B인" in page                                 # 본문의 < 가 태그로 읽히면 안 된다
    assert '<div id="tags">#태그하나 #태그둘 #태그셋 #태그넷 #태그다섯</div>' in page
    assert "작성 메모" not in page and "- 메모" not in page
    assert f"{P}도입부입니다.{E}\n{BLANK}\n{P}보험료율은" in page          # 문장 사이 빈 줄
    assert f"{P}· 항목 <b>강조</b>{E}\n{P}· 둘째 항목{E}" in page             # 목록은 붙어 있다

    tmd = md.replace("- 항목 **강조**\n- 둘째 항목", "| 가입기간 | 일수 |\n|---|---|\n| 1년 미만 | **120일** |")
    tpage, ttext = to_html(tmd), convert(tmd)
    assert "<table" in tpage and f"<th {CELL}>{SPAN}가입기간</span></th>" in tpage      # 표 셀도 크기·폰트를 단다
    assert "<p><br></p>" not in tpage                             # 크기 없는 빈 줄이 남으면 안 된다
    assert f"<td {CELL}>{SPAN}<b>120일</b></span></td>" in tpage and "|---" not in tpage and "---|" not in tpage
    assert "가입기간 — 일수\n1년 미만 — 120일" in ttext, ttext

    # 후보를 품은 자리는 전부 펼쳐진다. 후보 문장은 표시 없이 한 줄씩이라 남긴 줄을 그대로 쓸 수 있다
    omd = md.replace("## 첫 소제목", "[경험 한 줄 ① | A안(사실): 직접 **확인**했어요. | B안(해당될 때만): 저도 그랬어요.]\n\n"
                     "[내부 링크 | A안: 조건은 이 글에 있어요. | B안: 먼저 이 글을 보세요. | https://blog.naver.com/x/1]\n\n## 첫 소제목")
    otext, opage = convert(omd), to_html(omd)
    assert ("[경험 한 줄 ① — 문장 하나만 남기고 ▶ 줄과 나머지는 지우세요]\n▶ A안(사실)\n직접 확인했어요.\n"
            "▶ B안(해당될 때만)\n저도 그랬어요.") in otext, otext
    assert "▶ B안\n먼저 이 글을 보세요.\n▶ 아래 주소를 잘라내" in otext and otext.count("https://blog.naver.com/x/1") == 1, otext
    assert f"{P}직접 <b>확인</b>했어요.{E}\n{P}▶ B안(해당될 때만){E}" in opage
    assert "[경험 한 줄 ②]" in convert(md.replace("## 첫 소제목", "[경험 한 줄 ②]\n\n## 첫 소제목"))   # 후보 없는 옛 표기는 그대로
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1] == "--selftest":
        selftest()
    else:
        src = Path(sys.argv[1])
        out = src.with_name(src.stem + "_붙여넣기용.html")
        out.write_text(to_html(src.read_text(encoding="utf-8")), encoding="utf-8")
        print(out)
