"""네이버 원고용 대표 사진 후보 제안 — 공유마당(자유이용) + Pexels.

    python -X utf8 suggest_cover.py content/naver/04_실업급여-신청방법.md
    python -X utf8 suggest_cover.py --selftest

원고의 `## 작성 메모`에 `- 대표사진 검색어: 고용센터 | job center` 한 줄이 있어야 한다.
결과: _workspace/naver/cover_{순번}.html — 후보를 보고 골라 직접 내려받아 올린다.

언론사·정책브리핑 사진은 쓰지 않는다. 정책브리핑 저작권 안내에 "사진은 정부기관 및
연합뉴스 등에 저작권이 있으며 … 사전 협의"라고 되어 있다(2026-09-28 확인).
공유마당도 저작물마다 라이선스가 달라서 상업적 이용이 되는 표기만 통과시킨다.
"""
import base64
import html
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()
PEXELS_KEY = os.getenv("PEXELS_API_KEY")
GONGU = "https://gongu.copyright.or.kr"
OUT = Path(__file__).parent / "_workspace" / "naver"
UA = {"User-Agent": "Mozilla/5.0"}

# 목록의 photoCon_bottom 주석 → 출처 문구에 쓸 이름. 여기 없는 표기(공공누리 2~4유형,
# CC BY-NC 등)는 전부 버린다 — 모르는 표기를 통과시키는 쪽이 더 위험하다.
ALLOWED = {
    "KOGL(출처)": "공공누리 제1유형",
    "CCL(BY)": "CC BY",
    "기증(자유이용)": "기증 저작물",
}


def keywords(md: str) -> tuple[str, str] | None:
    m = re.search(r"^- 대표사진 검색어:\s*(.+?)\s*\|\s*(.+?)\s*$", md, flags=re.M)
    return (m.group(1), m.group(2)) if m else None


def parse_gongu(page: str) -> list[dict]:
    out = []
    for li in re.findall(r"<li>\s*<div class=\"bg_box\">(.*?)</li>", page, flags=re.S):
        lic = re.search(r"photoCon_bottom\">\s*<!-- (.+?) -->", li)
        sn = re.search(r"view\.do\?wrtSn=(\d+)", li)
        thumb = re.search(r"url\((/gongu/wrt/cmmn/wrtFileImageView\.do[^)]+)\)", li)
        fp = re.search(r"filePath=([A-Za-z0-9+/=]+)", thumb.group(1)) if thumb else None
        # filePath가 외부 URL이면 공유마당엔 사진이 없고 링크만 있다(썸네일은 빈 아이콘).
        # 2026-09-28 "고용센터" 결과 24개가 전부 이 경우였다.
        if (not (lic and sn) or lic.group(1) not in ALLOWED or not fp
                or base64.b64decode(fp.group(1) + "==").startswith(b"http")):
            continue
        head = re.search(r"photoCon_head\">(.*?)</div>", li, flags=re.S)
        author = re.search(r"<p class=\"tag\">(.*?)</p>", li, flags=re.S)
        title = re.sub(r"\s+", " ", re.sub(r"<!H[SE]>", "", head.group(1))).strip() if head else ""
        who = author.group(1).strip() if author else "저작자 미상"
        license_ = ALLOWED[lic.group(1)]
        out.append({
            "src": "공유마당",
            "thumb": GONGU + html.unescape(thumb.group(1)) if thumb else "",
            "page": f"{GONGU}/gongu/wrt/wrt/view.do?wrtSn={sn.group(1)}&menuNo=200023",
            "license": license_,
            "credit": f"사진: {title} / {who} / 공유마당({license_})",
        })
    return out


def search_gongu(words: str, limit=12) -> list[dict]:
    found = []
    for w in [x.strip() for x in words.split(",") if x.strip()]:
        r = requests.get(f"{GONGU}/gongu/wrt/wrtCl/listWrtImage.do?menuNo=200023&searchWrd={quote(w)}",
                         headers=UA, timeout=15)
        r.raise_for_status()
        found += parse_gongu(r.text)
    seen, uniq = set(), []
    for c in found:
        if c["page"] not in seen:
            seen.add(c["page"])
            uniq.append(c)
    return uniq[:limit]


def search_pexels(words: str, limit=6) -> list[dict]:
    if not PEXELS_KEY:
        raise RuntimeError("PEXELS_API_KEY 없음")
    r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": PEXELS_KEY},
                     params={"query": words, "per_page": limit, "orientation": "landscape"}, timeout=15)
    r.raise_for_status()
    return [{
        "src": "Pexels",
        "thumb": p["src"]["medium"],
        "page": p["url"],
        "license": "Pexels 라이선스(출처 표기 선택)",
        "credit": f"Photo: {p['photographer']} / Pexels",
    } for p in r.json().get("photos", [])]


def gallery(title: str, cands: list[dict]) -> str:
    cards = "\n".join(
        f'<figure><a href="{html.escape(c["page"])}" target="_blank" rel="noopener">'
        f'<img src="{html.escape(c["thumb"])}" loading="lazy"></a>'
        f'<figcaption><b>{html.escape(c["src"])}</b> · {html.escape(c["license"])}<br>'
        f'<code>{html.escape(c["credit"])}</code></figcaption></figure>'
        for c in cands)
    return f"""<!doctype html><meta charset="utf-8"><title>대표 사진 후보</title>
<style>body{{font-family:'Malgun Gothic',sans-serif;margin:24px;background:#fff;color:#222}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px}}
figure{{margin:0;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden}}
img{{width:100%;aspect-ratio:16/10;object-fit:cover;display:block}}
figcaption{{padding:10px 12px;font-size:13px;line-height:1.6}}code{{user-select:all}}</style>
<h2>{html.escape(title)}</h2>
<p>사진을 누르면 원본 페이지가 열립니다. 고른 사진 바로 아래에 출처 문구를 그대로 붙여 넣으세요.</p>
<div class="g">{cards}</div>"""


def run(path: str) -> int:
    md = Path(path).read_text(encoding="utf-8")
    kw = keywords(md)
    if not kw:
        print(f"'{path}' 작성 메모에 `- 대표사진 검색어: 한국어 | English` 줄을 추가하세요")
        return 1
    cands = []
    for name, fn, words in (("공유마당", search_gongu, kw[0]), ("Pexels", search_pexels, kw[1])):
        try:
            got = fn(words)
        except Exception as e:  # 한쪽이 죽어도 다른 쪽 후보는 낸다
            print(f"⚠ {name} 실패: {e}")
            got = []
        print(f"{name} {len(got)}개 ({words})")
        cands += got
    if not cands:
        return 1
    title = re.search(r"^제목: (.+)$", md, flags=re.M)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"cover_{Path(path).name.split('_')[0]}.html"
    out.write_text(gallery(title.group(1) if title else path, cands), encoding="utf-8")
    print(f"→ {out}")
    return 0


def selftest():
    """실측 목록 HTML 구조 그대로 — 허용 2종은 통과, 공공누리 2유형·외부 링크 항목은 버려야 한다."""
    hosted = base64.b64encode(b"/disk1/newdata/2026/x.jpg").decode()
    external = base64.b64encode(b"http://guro.grandculture.net/Contents?id=1").decode()

    def li(sn, title, who, lic, fp=hosted):
        return (f'<li>\n<div class="bg_box">\n<div class="img">\n<span class="ratioSet ratio-4x3">\n'
                f'<span class="ratioObject bg100p" style="background-image: url(/gongu/wrt/cmmn/'
                f'wrtFileImageView.do?wrtSn={sn}&thumbAt=Y&amp;thumbSe=t_thumb&filePath={fp});">\n</span></span>\n</div>\n'
                f'<div class="licsCon photoCon">\n<a href="/gongu/wrt/wrt/view.do?wrtSn={sn}&amp;menuNo=200023">\n'
                f'<div class="photoCon_head">\n{title}\n</div>\n</a>\n<p class="tag">\n{who}\n</p>\n'
                f'<div class="photoCon_bottom">\n\t\t <!-- {lic} --> <img alt="x">\n</div>\n</div>\n</div>\n</li>')
    page = (li(1, "서울관악<!HS>고용센터<!HE>", "저작자 미상", "KOGL(출처)")
            + li(2, "<!HS>고용센터<!HE> 입구", "홍길동", "KOGL(출처+상업금지)")
            + li(3, "구직 상담", "김아무개", "CCL(BY)")
            + li(4, "구로<!HS>고용센터<!HE>", "저작자 미상", "KOGL(출처)", external))
    got = parse_gongu(page)
    assert [c["page"].split("wrtSn=")[1].split("&")[0] for c in got] == ["1", "3"], got
    assert got[0]["credit"] == "사진: 서울관악고용센터 / 저작자 미상 / 공유마당(공공누리 제1유형)", got[0]["credit"]
    assert got[1]["license"] == "CC BY"
    assert "thumbSe=t_thumb" in got[0]["thumb"] and "&amp;" not in got[0]["thumb"]
    assert keywords("x\n- 대표사진 검색어: 고용센터, 구직 | job center\n") == ("고용센터, 구직", "job center")
    assert keywords("검색어 없음") is None
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif len(sys.argv) > 1:
        sys.exit(max(run(p) for p in sys.argv[1:]))
    else:
        print(__doc__)
