"""Threads 카드뉴스 렌더러: content/naver/cardnews/NN.json → assets/naver_img/NN_카드뉴스_k.png (1080x1080).

사용: python -X utf8 make_card_news.py NN | --selftest
슬라이드 종류: image(표지 등 완성 그림 + 선택 'AI 활용' 표시), table(2~3열), checklist.
넘친 슬라이드는 조용히 잘리지 않고 실패한다(2026-10-19 첫 렌더에서 푸터가 캔버스 밖으로 잘렸다).
"""
from __future__ import annotations

import html
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
SPEC_DIR = ROOT / "content" / "naver" / "cardnews"
OUT_DIR = ROOT / "assets" / "naver_img"
SIZE = 1080

# DESIGN_SKILLS.md 토큰(OKLCH, 강조색 1개). 글꼴은 이 PC에 설치된 것을 쓴다.
CSS = """
:root{--paper:oklch(97.5% .006 258);--rule:oklch(86% .010 258);--muted:oklch(45% .015 258);
--ink:oklch(20% .020 258);--accent:oklch(52% .19 258);
--display:"Gmarket Sans TTF Bold","Noto Sans KR","Malgun Gothic",sans-serif;
--body:"Noto Sans KR","Malgun Gothic",sans-serif}
*{box-sizing:border-box;margin:0}
body{font-family:var(--body);word-break:keep-all;overflow-wrap:anywhere;line-height:1.6;color:var(--ink)}
.s{width:1080px;height:1080px;padding:80px;display:flex;flex-direction:column;background:var(--paper);position:relative;overflow:hidden}
.d{font-family:var(--display);letter-spacing:-.02em}
.k{font-size:28px;color:var(--muted);margin-bottom:24px}
h2{font-size:56px;line-height:1.25;margin-bottom:40px;font-weight:700}
.t{display:grid;align-items:baseline;column-gap:24px;border-bottom:1px solid var(--rule)}
.t.h{font-size:28px;color:var(--muted);padding:16px 0;border-bottom:2px solid var(--ink)}
.t.h.big{border-bottom:0;padding:0}
.t span:not(:first-child){text-align:right}
.t3{padding:30px 0;font-size:38px}.t3 .n{font-family:var(--display);font-size:52px}
.t2{padding:30px 0}.t2 .a{font-size:40px;font-weight:600}.t2 .n{font-family:var(--display);font-size:60px;letter-spacing:-.03em}
.t3.sm{font-size:34px;padding:26px 0}.t3.sm .n{font-family:var(--body);font-size:34px;font-weight:600}
.t2.first{border-top:2px solid var(--ink)}
.t2.tight{padding:20px 0}
.t.hl .n.hot{color:var(--accent)}
.note{font-size:28px;color:var(--muted);margin-top:24px}
.f{margin-top:auto;display:flex;justify-content:space-between;font-size:26px;color:var(--muted)}
.ck{display:flex;gap:24px;align-items:baseline;padding:28px 0;border-bottom:1px solid var(--rule);font-size:42px;font-weight:600}
.ck i{font-style:normal;color:var(--accent);font-family:var(--display)}
.cta{margin-top:40px;background:var(--ink);color:var(--paper);border-radius:8px;padding:28px 36px;font-size:36px;font-weight:600}
.img{background-size:cover;background-position:center}
.ai{position:absolute;left:18px;bottom:18px;font:700 18px var(--body);color:#333;background:rgba(255,255,255,.82);padding:5px 12px;border-radius:14px}
"""


def _e(value: object) -> str:
    return html.escape(str(value))


def _footer(index: int, total: int, right: str | None) -> str:
    return f"<div class='f'><span>돈살림표</span><span>{_e(right) if right else f'{index} / {total}'}</span></div>"


def _head(slide: dict) -> str:
    return f"<p class='k'>{_e(slide['kicker'])}</p><h2 class='d'>{_e(slide['title'])}</h2>"


def render_slide(slide: dict, index: int, total: int, base: Path, check: bool = False) -> str:
    kind = slide["kind"]
    if kind == "image":
        src = (base / slide["src"]).resolve()
        if not src.is_file():
            if check:   # --check: 표지 그림 없이 나머지 슬라이드 넘침만 본다
                return "<section class='s'><p class='k'>표지 자리</p></section>"
            raise FileNotFoundError(f"표지 그림이 없습니다: {src}")
        badge = "<span class='ai'>AI 활용</span>" if slide.get("ai_badge") else ""
        return f"<section class='s img' style=\"background-image:url('{src.as_uri()}')\">{badge}</section>"
    if kind == "table":
        cols = len(slide["head"])
        assert cols in (2, 3), "table은 2~3열"
        compact = cols == 3 or slide.get("compact", False)   # 헤더 줄이 있는 작은 표
        grid = "1fr auto" if cols == 2 else "1.1fr 1fr 1fr"
        hl = slide.get("highlight")
        head = (
            "" if not compact else
            f"<div class='t h' style='grid-template-columns:{grid}'>"
            + "".join(f"<span>{_e(h)}</span>" for h in slide["head"]) + "</div>"
        )
        rows = []
        for i, row in enumerate(slide["rows"]):
            cls = ("t t3" + (" sm" if slide.get("small") else "")) if compact else (
                "t t2" + (" tight" if len(slide["rows"]) > 3 else ""))
            first = " first" if not compact and i == 0 else ""
            lit = " hl" if i == hl else ""
            cells = "".join(
                f"<span class='{'a' if j == 0 else 'n'}{' hot' if j == slide.get('hot_col', 1) else ''}'>{_e(c)}</span>"
                for j, c in enumerate(row)
            )
            rows.append(f"<div class='{cls}{first}{lit}' style='grid-template-columns:{grid}'>{cells}</div>")
        note = f"<p class='note'>{_e(slide['note'])}</p>" if slide.get("note") else ""
        return (f"<section class='s'>{_head(slide)}{head}{''.join(rows)}{note}"
                f"{_footer(index, total, slide.get('footer_right'))}</section>")
    if kind == "checklist":
        items = "".join(f"<div class='ck'><i>{n}</i><span>{_e(t)}</span></div>" for n, t in enumerate(slide["items"], 1))
        cta = f"<div class='cta'>{_e(slide['cta'])}</div>" if slide.get("cta") else ""
        return (f"<section class='s'>{_head(slide)}{items}{cta}"
                f"{_footer(index, total, slide.get('footer_right'))}</section>")
    raise ValueError(f"알 수 없는 슬라이드 종류: {kind}")


def render(spec: dict, out_dir: Path, base: Path, check: bool = False) -> list[Path]:
    slides = spec["slides"]
    assert 2 <= len(slides) <= 10, "카드뉴스는 2~10장"
    body = "".join(render_slide(s, i, len(slides), base, check) for i, s in enumerate(slides, 1))
    outputs: list[Path] = []
    # about:blank 페이지는 file:// 그림을 못 읽어서 표지가 빈 7KB 파일로 나왔다. 실제 파일로 열어야 한다.
    page_file = Path(tempfile.mkdtemp()) / "cards.html"
    page_file.write_text(f"<meta charset='utf-8'><style>{CSS}</style>{body}", encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": SIZE, "height": SIZE})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(500)
        for i, element in enumerate(page.query_selector_all("section.s"), 1):
            overflow = page.evaluate("e=>e.scrollHeight-e.clientHeight", element)
            if overflow > 0:
                browser.close()
                raise SystemExit(f"{i}번 슬라이드가 {overflow}px 넘칩니다. 글을 줄이세요.")
            out = out_dir / f"{spec['number']}_카드뉴스_{i}.png"
            element.screenshot(path=str(out))
            outputs.append(out)
        browser.close()
    return outputs


def selftest() -> None:
    spec = {"number": 999, "slides": [
        {"kind": "table", "kicker": "k", "title": "제목", "head": ["a", "b"], "rows": [["가", "1%"], ["나", "2%"]]},
        {"kind": "checklist", "kicker": "k", "title": "제목", "items": ["하나", "둘"], "cta": "링크"},
    ]}
    with tempfile.TemporaryDirectory() as tmp:
        files = render(spec, Path(tmp), ROOT)
        assert [f.name for f in files] == ["999_카드뉴스_1.png", "999_카드뉴스_2.png"]
        assert all(f.read_bytes()[16:24] == (SIZE).to_bytes(4, "big") * 2 for f in files), "1080x1080"
        cover = Path(tmp) / "c.png"
        cover.write_bytes((ROOT / "content/naver/cardnews/18_cover_canva.png").read_bytes())
        [image] = render({"number": 998, "slides": [
            {"kind": "image", "src": "c.png", "ai_badge": True}, spec["slides"][0]]}, Path(tmp), Path(tmp))[:1]
        assert image.stat().st_size > 100_000, "그림 표지가 비어 있다(file:// 그림 로드 실패)"
        try:
            render({"number": 997, "slides": [{"kind": "image", "src": "nope.png"}, spec["slides"][1]]},
                   Path(tmp), Path(tmp))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("없는 표지 그림이 빈 슬라이드로 저장됐다")
        spec["slides"][0]["title"] = "아주 긴 제목 " * 40
        try:
            render(spec, Path(tmp), ROOT)
        except SystemExit as exc:
            assert "넘칩니다" in str(exc)
        else:
            raise AssertionError("넘친 슬라이드를 잡지 못했다")
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif len(sys.argv) in (2, 3) and sys.argv[1].isdigit() and sys.argv[2:] in ([], ["--check"]):
        number = int(sys.argv[1])
        check = sys.argv[2:] == ["--check"]
        spec_path = SPEC_DIR / f"{number:02d}.json"   # 글 파일명(08_…)과 같은 두 자리
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        assert spec["number"] == number, f"{spec_path.name}의 number가 {number}와 다르다"
        target = Path(tempfile.mkdtemp()) if check else OUT_DIR
        for path in render(spec, target, ROOT, check):
            print(path if check else path.relative_to(ROOT), path.stat().st_size // 1024, "KB")
    else:
        sys.exit("사용법: make_card_news.py NN [--check] | --selftest")
