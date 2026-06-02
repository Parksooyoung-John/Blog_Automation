"""
Harness _workspace/02_blog_post.md → Notion DB "발행대기" 업로드
- 마크다운 → HTML 변환
- [이미지 위치: ...] 플레이스홀더를 실제 이미지로 교체 (Pexels → DALL-E 폴백)
- Notion 페이지 블록으로 분할 저장
- 03_tistory_playwright.py가 이 항목을 감지해서 Tistory에 발행
"""

import os
import re
import math
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    import markdown as md_lib
except ImportError:
    raise SystemExit("markdown 패키지가 없습니다. pip install markdown 후 재실행하세요.")

load_dotenv()

NOTION_KEY    = os.getenv("NOTION_API_KEY")
NOTION_DB_ID  = os.getenv("NOTION_DATABASE_ID")
OPENAI_KEY    = os.getenv("OPENAI_API_KEY")
PEXELS_KEY    = os.getenv("PEXELS_API_KEY", "")

# Notion DB의 제목 컬럼명 (DB 설정에 따라 '이름' 또는 '제목')
TITLE_PROPERTY = "이름"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

BLOG_POST_PATH = Path(__file__).parent / "_workspace" / "02_blog_post.md"
CHUNK_SIZE = 1900  # Notion rich_text 블록당 최대 2000자, 여유분 포함
INPUT_PATH = Path(__file__).parent / "_workspace" / "00_input.md"

# 블로그 카테고리 자동 분류 규칙
# Notion select는 쉼표 불허 → Notion 저장명(쉼표 없음) 사용
# 실제 Tistory 카테고리명은 03_tistory_playwright.py의 TISTORY_CATEGORY_MAP에서 매핑
CATEGORY_RULES = [
    (["ISA", "IRP", "연금", "절세", "세금우대", "소득공제"],            "절세연금"),
    (["보험", "실손", "생명보험"],                                       "보험비교"),
    (["대출", "주택담보", "전세자금", "금리", "이자율", "HUG", "HF", "SGI", "전세보증", "버팀목"], "대출금리"),
    (["주식", "ETF", "펀드", "투자", "코스피", "나스닥"],                "주식ETF"),
    (["청년", "정부지원", "지원금", "보조금"],                           "정부지원금"),
    (["신용카드", "카드혜택", "캐시백"],                                 "신용카드"),
    (["ChatGPT", "Claude", "Gemini", "Copilot", "소프트웨어 비교"],     "소프트웨어 비교"),
    (["자동화", "파이썬", "Python", "노코드", "Make.com"],              "업무자동화"),
    (["AI 도구", "AI 활용", "프롬프트", "챗봇"],                        "AI 도구활용"),
    (["부업", "수익화", "프리랜서", "N잡"],                              "AI부업수익화"),
]

# blog-writer가 출력하는 이미지 플레이스홀더 패턴
# 예: [이미지 위치: 인지편향 다이어그램 — alt: "인지편향 소비 패턴"]
IMAGE_PATTERN = re.compile(r'\[이미지 위치: (.+?) — alt: "(.+?)"\]')


# ═══════════════════════════════════════════════════════
# 이미지 처리
# ═══════════════════════════════════════════════════════

def _fetch_pexels(query: str) -> str | None:
    """Pexels에서 키워드로 이미지 URL 검색"""
    if not PEXELS_KEY:
        return None
    try:
        res = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            timeout=10,
        )
        if res.status_code != 200:
            return None
        photos = res.json().get("photos", [])
        return photos[0]["src"]["large"] if photos else None
    except Exception:
        return None


def _generate_dalle(description: str) -> str | None:
    """gpt-image-1로 이미지 생성 후 data URI 반환"""
    if not OPENAI_KEY:
        return None
    try:
        import base64
        res = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-image-1",
                "prompt": (
                    f"블로그 본문 이미지, 주제: '{description}'. "
                    "전문적이고 깔끔한 일러스트, 텍스트 없음, 16:9 비율, 한국 블로그 스타일"
                ),
                "n": 1,
                "size": "1536x1024",
            },
            timeout=60,
        )
        if res.status_code != 200:
            return None
        b64 = res.json()["data"][0]["b64_json"]
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def replace_image_placeholders(html: str) -> str:
    """[이미지 위치: desc — alt: "alt"] 패턴 처리.
    비용 정책: Pexels(무료) 우선 → Pexels 없으면 플레이스홀더 제거.
    DALL-E 본문 이미지 생성 비활성화 (대표이미지 1장만 03_tistory_playwright.py에서 생성).
    """
    def replacer(m: re.Match) -> str:
        description, alt = m.group(1).strip(), m.group(2).strip()

        url = _fetch_pexels(description)
        if url:
            print(f"  이미지 처리: {description[:45]} → Pexels")
            return (
                f'<figure style="margin:24px 0;">'
                f'<img src="{url}" alt="{alt}" style="max-width:100%;border-radius:8px;">'
                f'</figure>'
            )
        # Pexels 없으면 플레이스홀더 제거 (DALL-E 비용 절감)
        print(f"  이미지 건너뜀: {description[:45]}")
        return ""

    return IMAGE_PATTERN.sub(replacer, html)


def detect_category(title: str) -> str:
    """제목 키워드로 Tistory 카테고리 자동 분류"""
    for keyword_list, category in CATEGORY_RULES:
        for kw in keyword_list:
            if kw in title:
                return category
    return ""


def extract_tags(title: str) -> list[str]:
    """00_input.md 키워드 + 제목 단어로 태그 생성 (최대 15개)"""
    tags: list[str] = []
    if INPUT_PATH.exists():
        text = INPUT_PATH.read_text(encoding="utf-8")
        m = re.search(r'^## 키워드\s*\n(.+)$', text, re.MULTILINE)
        if m:
            for kw in m.group(1).split(","):
                kw = kw.strip()
                if kw and kw not in tags:
                    tags.append(kw)
    for word in re.split(r'[\s·—\-\[\]().,]', title):
        word = word.strip()
        if len(word) >= 2 and word not in tags:
            tags.append(word)
    return tags[:15]


def ensure_db_properties():
    """Notion DB에 카테고리/태그 프로퍼티가 없으면 자동 추가"""
    res = requests.get(f"https://api.notion.com/v1/databases/{NOTION_DB_ID}", headers=NOTION_HEADERS)
    if res.status_code != 200:
        return
    existing = set(res.json().get("properties", {}).keys())
    updates: dict = {}
    if "카테고리" not in existing:
        updates["카테고리"] = {"select": {}}
    if "태그" not in existing:
        updates["태그"] = {"multi_select": {}}
    if updates:
        requests.patch(
            f"https://api.notion.com/v1/databases/{NOTION_DB_ID}",
            headers=NOTION_HEADERS,
            json={"properties": updates},
        )
        print(f"  Notion DB 프로퍼티 추가: {list(updates.keys())}")


# ═══════════════════════════════════════════════════════
# 마크다운 파싱
# ═══════════════════════════════════════════════════════

def parse_blog_post(path: Path) -> tuple[str, str]:
    """마크다운 파일에서 (제목, HTML본문) 추출 + 이미지 플레이스홀더 교체"""
    text = path.read_text(encoding="utf-8")

    # H1에서 제목 추출
    m = re.search(r'^# (.+)$', text, re.MULTILINE)
    title = m.group(1).strip() if m else "제목없음"

    # H1 제거, 메타 블록쿼트(> **...**) 제거
    body = re.sub(r'^# .+\n', '', text, count=1, flags=re.MULTILINE)
    body = re.sub(r'^>.*\n?', '', body, flags=re.MULTILINE).strip()

    # blog-writer가 추가하는 메타 블록 제거 (본문에 노출되면 안 되는 내용)
    body = re.sub(r'\[THUMBNAIL_PROMPT\].*?\[/THUMBNAIL_PROMPT\]', '', body, flags=re.DOTALL)
    body = body.strip()

    # 마크다운 → HTML
    html = md_lib.markdown(body, extensions=["tables", "fenced_code", "nl2br"])

    # 이미지 플레이스홀더 → 실제 이미지
    html = replace_image_placeholders(html)

    return title, html


# ═══════════════════════════════════════════════════════
# Notion 업로드
# ═══════════════════════════════════════════════════════

def make_paragraph_blocks(html: str) -> list:
    """HTML 문자열을 Notion paragraph 블록 목록으로 변환 (청크 분할)"""
    blocks = []
    for i in range(0, len(html), CHUNK_SIZE):
        chunk = html[i:i + CHUNK_SIZE]
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            },
        })
    return blocks


def create_notion_page(title: str, html: str, category: str = "", tags: list | None = None) -> str:
    """Notion DB에 '발행대기' 페이지 생성, 생성된 page_id 반환"""
    blocks = make_paragraph_blocks(html)
    first_batch, rest = blocks[:100], blocks[100:]

    properties: dict = {
        TITLE_PROPERTY: {"title": [{"type": "text", "text": {"content": title}}]},
        "상태": {"select": {"name": "발행대기"}},
        "날짜": {"date": {"start": date.today().isoformat()}},
    }
    if category:
        properties["카테고리"] = {"select": {"name": category}}
    if tags:
        properties["태그"] = {"multi_select": [{"name": t} for t in tags]}

    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": properties,
        "children": first_batch,
    }

    res = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload)
    if res.status_code != 200:
        raise RuntimeError(f"Notion 페이지 생성 실패 ({res.status_code}): {res.text}")

    page_id = res.json()["id"]

    for i in range(0, len(rest), 100):
        r2 = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            json={"children": rest[i:i + 100]},
        )
        r2.raise_for_status()

    return page_id


def main():
    if not BLOG_POST_PATH.exists():
        raise SystemExit(f"파일이 없습니다: {BLOG_POST_PATH}\n/content-repurposer 실행 후 재시도하세요.")

    pexels_status = "사용 가능" if PEXELS_KEY else "키 없음 (DALL-E 폴백)"
    print(f"이미지 소스: Pexels({pexels_status}) [DALL-E 본문 이미지 비활성화 — 비용 절감]")
    print(f"읽는 중: {BLOG_POST_PATH}")

    ensure_db_properties()
    title, html = parse_blog_post(BLOG_POST_PATH)
    category = detect_category(title)
    tags = extract_tags(title)

    print(f"제목: {title}")
    print(f"카테고리: {category or '(미분류)'}")
    print(f"태그 ({len(tags)}개): {', '.join(tags)}")
    print(f"HTML 길이: {len(html)}자 → {math.ceil(len(html)/CHUNK_SIZE)}개 블록")

    page_id = create_notion_page(title, html, category, tags)
    print(f"\nNotion 업로드 완료! (상태: 발행대기)")
    print(f"  Page ID: {page_id}")
    print(f"\n다음 단계: python -X utf8 03_tistory_playwright.py")


if __name__ == "__main__":
    main()
