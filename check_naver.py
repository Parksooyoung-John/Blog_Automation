"""네이버 원고 검수 — 분량·소제목·이미지·경험·내부링크·태그, 그리고 티스토리 문장 중복.

    python -X utf8 check_naver.py
    python -X utf8 check_naver.py --selftest

⚠ 원고의 플레이스홀더 표기를 바꾸면 여기 정규식도 같이 봐야 한다.
2026-09-26에 표기가 `[이미지: ...]`에서 `[이미지 ①: ...]`로 바뀌었는데 정규식이 콜론을
고정하고 있어서, 이미지·경험을 0으로 세고 분량은 플레이스홀더까지 포함해 부풀려 잡았다.
오류를 내지 않고 조용히 틀린 값을 보고했다. `--selftest`가 그 재발을 막는다.
"""
import glob
import os
import re
import sys
import tempfile

PLACEHOLDERS = r'\[(이미지|경험 한 줄|내부 링크)[^\]]*\]'


def parts(path):
    n = open(path, encoding='utf-8').read()
    b = n.split('## 작성 메모')[0]
    tags = re.findall(r'#[가-힣A-Za-z0-9]+', b)
    b2 = re.sub(r'^제목:.*$', '', b, flags=re.M)
    b2 = re.sub(r'^#[가-힣A-Za-z0-9]+.*$', '', b2, flags=re.M)
    c = re.sub(PLACEHOLDERS, '', b2, flags=re.S)
    c = re.sub(r'^-{3,}$', '', c, flags=re.M)
    return n, b2, c, tags


def sents(x):
    x = re.sub(r'[#*>|\-]', '', x)
    return {s.strip() for s in re.split(r'[.!?]\s|\n', x) if len(s.strip()) >= 12}


def measure(path, tistory):
    n, b, c, tags = parts(path)
    m = re.search(r'^제목: (.+)$', n, flags=re.M)
    if not m:
        return None
    return {
        "title": m.group(1),
        "chars": len(c.strip()),
        "heads": len(re.findall(r'^## ', b, flags=re.M)),
        "images": len(re.findall(r'\[이미지', b)),
        "exp": len(re.findall(r'\[경험 한 줄', b)),
        "links": len(re.findall(r'\[내부 링크', b)),
        "tags": tags,
        "dup": sents(c) & tistory,
    }


def passes(r):
    return (800 <= r["chars"] <= 1600 and 3 <= r["heads"] <= 5 and r["images"] >= 2
            and r["exp"] >= 1 and r["links"] >= 1 and 8 <= len(r["tags"]) <= 12
            and not r["dup"])


def selftest():
    """실제 원고에 쓰는 표기법 그대로 넣어 카운트가 맞는지 본다."""
    doc = (
        "제목: 테스트 제목\n\n---\n\n"
        "[이미지 ①: `assets/x.png` — 제작 완료]\n\n"
        "도입 문단입니다. 충분히 길게 씁니다.\n\n"
        "[경험 한 줄 ①]\n\n"
        "## 소제목 하나\n\n본문입니다.\n\n"
        "[이미지 ②: **직접 캡처 필요** — 어쩌고]\n\n"
        "## 소제목 둘\n\n본문입니다.\n\n"
        "## 소제목 셋\n\n본문입니다.\n\n"
        "[내부 링크: 아래 문장을 쓰고 줄을 바꾼 뒤 이 주소를 붙여넣으면 카드가 생성됩니다\n"
        "            ⚠ 문장 중간에 붙여넣지 말 것 → https://blog.naver.com/education_blog/1]\n\n"
        "아래 글을 보세요.\n\n"
        "[경험 한 줄 ②]\n\n"
        "#태그1 #태그2 #태그3 #태그4 #태그5 #태그6 #태그7 #태그8 #태그9 #태그10\n\n"
        "---\n\n## 작성 메모 (발행 시 삭제)\n\n- 메모는 세지 않는다\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.md")
        open(path, "w", encoding="utf-8").write(doc)
        r = measure(path, set())

    assert r["title"] == "테스트 제목", r["title"]
    assert r["images"] == 2, f"이미지 {r['images']}"
    assert r["exp"] == 2, f"경험 {r['exp']}"
    assert r["links"] == 1, f"내부링크 {r['links']}"
    assert r["heads"] == 3, f"소제목 {r['heads']}"
    assert len(r["tags"]) == 10, f"태그 {len(r['tags'])}"
    # 플레이스홀더·태그·작성 메모가 글자수에 섞이면 안 된다 (본문은 100자 남짓)
    assert r["chars"] < 120, f"플레이스홀더가 글자수에 섞였다: {r['chars']}"
    print("selftest ok")


def main():
    tistory = sents("".join(open(f, encoding='utf-8').read()
                            for f in glob.glob('_workspace/02_blog_post_*.md')))
    allok = True
    for p in sorted(glob.glob('content/naver/*.md')):
        r = measure(p, tistory)
        if r is None:          # 제목 줄이 없으면 원고가 아니다(메모·프롬프트 파일)
            continue
        ok = passes(r)
        allok &= ok
        print(('OK   ' if ok else 'CHECK'), os.path.basename(p))
        print(f"       {r['chars']}자 / 소제목 {r['heads']} / 이미지 {r['images']}"
              f" / 경험 {r['exp']} / 내부링크 {r['links']}"
              f" / 태그 {len(r['tags'])} / 티스토리 중복 {len(r['dup'])}")
        print(f"       제목: {r['title']}")
        for d in list(r["dup"])[:3]:
            print('         중복:', d[:55])
    print('\n전체 통과' if allok else '\n확인 필요')
    return 0 if allok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        sys.exit(main())
