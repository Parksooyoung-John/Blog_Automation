"""네이버 발행 준비를 명령 하나로 — 검수 → 카드 → 썸네일 → 붙여넣기 파일 → 이미지 폴더.

에디터 앞에서 멈춘다. 붙여넣기와 발행은 사람이 한다(NAVER_GUIDE.md 절대 규칙).
대표 사진도 고르지 않는다 — 후보 갤러리만 열고, 사용자가 저장한 cover_NN 파일을 쓴다.

    python -X utf8 naver_prep.py 14
    python -X utf8 naver_prep.py --selftest
"""
import glob
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

import check_naver
import make_naver_images as cards
import naver_paste
import suggest_cover

ROOT = Path(__file__).parent
WS = ROOT / "_workspace" / "naver"


def image_paths(md: str) -> list:
    """원고 본문에 적힌 이미지 파일을 나온 순서대로. 에디터에 넣는 순서다."""
    body = md.split("## 작성 메모")[0]
    return list(dict.fromkeys(re.findall(r"assets/naver_img/[^`\s\]]+\.png", body)))


def cover_hint(md: str, num: str):
    """대표 그림이 없을 때의 안내. scene(AI 그림)은 사진 갤러리가 아니라 --gen 후보에서 고른다.

    2026-10-20 새 작업폴더에서 cover_20.png가 없었는데 '대표사진 검색어 줄을 추가하라'는 엉뚱한 안내가 나왔다."""
    if check_naver.memo_value(md, "썸네일 유형") == "scene":
        return (f"scene 썸네일이라 사진 갤러리는 열지 않습니다 — _workspace/naver/cover_{num}.png가 없습니다. "
                f"새로 만들려면 `python -X utf8 make_naver_images.py --gen {num}`(후보 4장, 약 $0.05), "
                f"이미 만들었다면 다른 작업 폴더의 cover_{num}*.png를 이 폴더 _workspace/naver로 복사하세요")
    return None


def branch() -> str:
    return subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def prep(num: str) -> int:
    # 2026-10-16 다른 세션이 이 폴더를 SNS 브랜치(codex/canva-rest-oauth)로 바꿔 두었고, 다음 블로그 작업이 그 위에서 시작됐다.
    if branch() != "main":
        print(f"이 폴더가 '{branch()}' 브랜치다 — 블로그 작업은 main에서. git checkout main && git pull 후 다시 실행")
        return 1
    drafts = sorted((ROOT / "content" / "naver").glob(f"{num}_*.md"))
    if not drafts:
        print(f"content/naver/{num}_*.md 원고가 없습니다")
        return 1
    src = drafts[0]
    md = src.read_text(encoding="utf-8")

    tistory = check_naver.sents("".join(Path(f).read_text(encoding="utf-8")
                                        for f in glob.glob(str(ROOT / "_workspace" / "02_blog_post_*.md"))))
    if not check_naver.passes(check_naver.measure(str(src), tistory, check_naver.load_volumes())):
        print(f"검수 미통과 — python -X utf8 check_naver.py 로 {src.name} 항목을 확인하세요")
        return 1
    print("1. 검수 통과")

    imgs = image_paths(md)
    thumb = f"assets/naver_img/{num}_썸네일.png"
    todo = {Path(p).stem: cards.CARDS[Path(p).stem] for p in imgs
            if p != thumb and not (ROOT / p).exists() and Path(p).stem in cards.CARDS}
    if todo:
        with cards.sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            broken = cards.shoot_cards(b.new_page(device_scale_factor=2), todo)
            b.close()
        if broken:
            return 1
    print(f"2. 카드 {len(todo)}장 새로 생성")

    if not cards.find_cover(num):
        hint = cover_hint(md, num)
        if hint:
            print(f"3. {hint}")
            return 1
        suggest_cover.run(str(src))
        webbrowser.open((WS / f"cover_{num}.html").as_uri())
        print(f"3. 대표 사진을 골라 _workspace/naver/cover_{num}.jpg 로 저장한 뒤 다시 실행하세요")
        return 1
    if cards.thumb_cmd(num):
        return 1
    print(f"3. 썸네일 생성 — 사진 아래 출처 문구는 cover_{num}.html 갤러리에서 복사")

    missing = [p for p in imgs if not (ROOT / p).exists()]
    if missing:
        print("이미지 파일이 없습니다:", ", ".join(missing))
        return 1

    page = src.with_name(src.stem + "_붙여넣기용.html")
    page.write_text(naver_paste.page_for(src), encoding="utf-8")

    out = WS / f"publish_{num}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for i, p in enumerate(imgs, 1):
        shutil.copy(ROOT / p, out / f"{i}_{Path(p).name}")
    print(f"4. 이미지 {len(imgs)}장 → {out} (번호 순서대로 넣으면 됩니다)")

    webbrowser.open(page.as_uri())
    print(f"5. {page.name} 을 열었습니다 — [본문 복사] 후 에디터에 붙여넣으세요. 발행 뒤에는 python -X utf8 verify_naver.py")
    return 0


def selftest():
    md = ("제목: 테스트\n\n[이미지 ①: 제목 썸네일 — 결과 `assets/naver_img/13_썸네일.png`를 넣고 출처를 붙입니다]\n\n본문.\n\n"
          "[이미지 ②: `assets/naver_img/32_연말정산_월세_공제액.png` — 제작 완료]\n\n## 소제목\n\n"
          "[이미지 ③: `assets/naver_img/33_연말정산_월세_조건.png` — 제작 완료]\n\n"
          "## 작성 메모 (발행 시 삭제)\n\n- 카드 `assets/naver_img/99_메모에만.png`\n")
    assert image_paths(md) == ["assets/naver_img/13_썸네일.png", "assets/naver_img/32_연말정산_월세_공제액.png",
                               "assets/naver_img/33_연말정산_월세_조건.png"], image_paths(md)
    assert "--gen 20" in cover_hint("- 썸네일 유형: scene\n- 글 유형: 계산·실수령형\n", "20")
    assert cover_hint("- 썸네일 유형: card\n", "20") is None      # card는 사진 갤러리 경로를 그대로 쓴다
    # 붙여넣기 파일이 원고 편 번호의 서식으로 나오는지 — 18편이 15px·템플릿 없이 나왔다(2026-10-17)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        for name, px in (("18_t.md", "19"), ("15_t.md", "16"), ("14_t.md", "15")):
            (Path(d) / name).write_text(md.replace("## 작성 메모", "#가 #나 #다 #라 #마\n\n---\n\n## 작성 메모"), encoding="utf-8")
            html = naver_paste.page_for(Path(d) / name)
            assert f"font-size:{px}px" in html, (name, px)
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1] == "--selftest":
        selftest()
    else:
        sys.exit(prep(sys.argv[1]))
