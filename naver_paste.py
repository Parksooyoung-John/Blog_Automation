"""네이버 원고(.md) → 스마트에디터 붙여넣기용 .txt.

마크다운 기호를 지워 에디터에 그대로 붙여넣을 수 있게 만든다.

    python -X utf8 naver_paste.py content/naver/02_실업급여-조건.md
    python -X utf8 naver_paste.py --selftest
"""
import re
import sys
from pathlib import Path

# 해시태그 줄: '#실업급여 #실업급여조건 ...'. '## 소제목'과 헷갈리면 안 된다.
TAG_RE = re.compile(r"^#\S+(?: +#\S+)+$", re.M)

CHECKLIST = """
═══════════════════════════════════════
발행 전 체크
═══════════════════════════════════════
· 태그 10개 입력 — 1편에서 빠뜨렸던 항목이다. 발행 설정 창에서 확인
· [소제목] 줄은 '인용구' 스타일 적용 후 표시는 지우기 (앞뒤 빈 줄은 넣지 말 것)
· [이미지] 자리에 PNG 넣기. 첫 이미지가 썸네일이 된다
· [경험 한 줄] 두 곳 채우기 — 가장 중요
· 발행 설정: 카테고리 / 주제 비즈니스·경제 / 전체공개 / 검색허용 체크
"""


def convert(md: str) -> str:
    body = md.split("## 작성 메모")[0]
    title = re.search(r"^제목: (.+)$", body, re.M).group(1).strip()
    m = TAG_RE.search(body)
    tags = m.group(0).strip() if m else ""

    body = re.sub(r"^제목: .+$", "", body, flags=re.M)
    body = TAG_RE.sub("", body)
    body = re.sub(r"^-{3,}$", "", body, flags=re.M)
    body = re.sub(r"^#{2,} (.+)$", r"[소제목] \1", body, flags=re.M)
    body = re.sub(r"^- ", "· ", body, flags=re.M)
    body = body.replace("**", "").replace("`", "")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    assert "##" not in body, "소제목 변환 실패"
    assert tags.startswith("#") and tags.count("#") >= 5, f"태그 추출 실패: {tags!r}"

    return (
        "제목 (그대로 복사해서 제목칸에 붙여넣기)\n" + title + "\n\n"
        "═══════════════════════════════════════\n본문 (아래부터 복사)\n"
        "═══════════════════════════════════════\n\n" + body + "\n\n"
        "═══════════════════════════════════════\n태그 (하나씩 엔터로 입력 · 띄어쓰기 없이)\n"
        "═══════════════════════════════════════\n" + tags + "\n" + CHECKLIST
    )


def selftest():
    out = convert(
        "제목: 테스트 제목\n\n---\n\n도입부입니다.\n\n## 첫 소제목\n\n- 항목 **강조**\n\n"
        "#태그하나 #태그둘 #태그셋 #태그넷 #태그다섯\n"
    )
    assert "[소제목] 첫 소제목" in out
    assert "· 항목 강조" in out
    assert out.rstrip().endswith("검색허용 체크")
    assert "#태그하나 #태그둘 #태그셋 #태그넷 #태그다섯" in out
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1] == "--selftest":
        selftest()
    else:
        src = Path(sys.argv[1])
        out = src.with_name(src.stem + "_붙여넣기용.txt")
        out.write_text(convert(src.read_text(encoding="utf-8")), encoding="utf-8")
        print(out)
