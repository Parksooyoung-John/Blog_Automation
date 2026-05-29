"""
티스토리 포스팅 후처리 스크립트
기능:
  1. Notion DB에서 '발행완료' 상태 포스팅 감지
  2. DALL-E API로 썸네일 이미지 자동 생성
  3. 생성 이미지를 티스토리에 업로드 후 포스트에 삽입
  4. 쿠팡 파트너스 키워드 링크 자동 삽입
  5. SEO 메타 최적화 (제목 보강, 태그 추가)
  6. Notion 상태를 '전체완료'로 업데이트
"""

import os
import re
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── 환경변수 ──────────────────────────────────────────
TISTORY_TOKEN   = os.getenv("TISTORY_ACCESS_TOKEN")
TISTORY_BLOG    = os.getenv("TISTORY_BLOG_NAME")
NOTION_KEY      = os.getenv("NOTION_API_KEY")
NOTION_DB_ID    = os.getenv("NOTION_DATABASE_ID")
OPENAI_KEY      = os.getenv("OPENAI_API_KEY")
COUPANG_ID      = os.getenv("COUPANG_PARTNER_ID", "")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# ── 쿠팡 파트너스 키워드 맵 (역사심리학 특화) ──────────
COUPANG_KEYWORD_MAP = {
    "심리학": "https://link.coupang.com/re/AFFILCODE?itemId=YOUR_ITEM_ID",  # 심리학 책
    "역사": "https://link.coupang.com/re/AFFILCODE?itemId=YOUR_ITEM_ID2",   # 역사 책
    "인지": "https://link.coupang.com/re/AFFILCODE?itemId=YOUR_ITEM_ID3",
    "행동": "https://link.coupang.com/re/AFFILCODE?itemId=YOUR_ITEM_ID4",
}

# ── 1. Notion: 발행완료 & 이미지처리 대기 항목 조회 ──────
def fetch_pending_posts():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    payload = {
        "filter": {
            "and": [
                {"property": "상태", "select": {"equals": "발행완료"}},
                # 이미지 처리 여부 컬럼이 있다면 추가 필터
                # {"property": "이미지처리", "checkbox": {"equals": False}},
            ]
        }
    }
    res = requests.post(url, headers=NOTION_HEADERS, json=payload)
    res.raise_for_status()
    return res.json().get("results", [])


# ── 2. Notion: 페이지 상세 정보 가져오기 ──────────────────
def get_notion_page(page_id: str) -> dict:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    res = requests.get(url, headers=NOTION_HEADERS)
    res.raise_for_status()
    return res.json()


def get_notion_page_content(page_id: str) -> str:
    """Notion 블록을 순서대로 읽어 텍스트로 합침"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    res = requests.get(url, headers=NOTION_HEADERS)
    res.raise_for_status()
    blocks = res.json().get("results", [])

    texts = []
    for block in blocks:
        btype = block.get("type")
        if btype in ("paragraph", "heading_1", "heading_2", "heading_3",
                     "bulleted_list_item", "numbered_list_item"):
            rich_texts = block.get(btype, {}).get("rich_text", [])
            line = "".join(rt.get("plain_text", "") for rt in rich_texts)
            texts.append(line)
    return "\n".join(texts)


# ── 3. DALL-E로 썸네일 이미지 생성 ────────────────────────
def generate_thumbnail(title: str) -> bytes:
    """제목을 기반으로 썸네일 이미지 생성 후 바이너리 반환"""
    prompt = (
        f"블로그 썸네일 이미지, 주제: '{title}'. "
        "고급스럽고 전문적인 느낌, 한국 블로그 스타일, "
        "텍스트 없이 일러스트레이션 또는 사진 스타일, 16:9 비율"
    )
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": "1792x1024",  # 16:9에 가까운 사이즈
        "quality": "standard",
        "response_format": "url",
    }
    res = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers=headers,
        json=payload,
    )
    res.raise_for_status()
    image_url = res.json()["data"][0]["url"]

    # 이미지 다운로드
    img_res = requests.get(image_url)
    img_res.raise_for_status()
    return img_res.content


# ── 4. 티스토리에 이미지 업로드 ───────────────────────────
def upload_image_to_tistory(image_bytes: bytes, filename: str) -> str:
    """이미지를 티스토리에 업로드하고 URL 반환"""
    url = "https://www.tistory.com/apis/post/attach"
    files = {"uploadedfile": (filename, image_bytes, "image/png")}
    params = {
        "access_token": TISTORY_TOKEN,
        "blogName": TISTORY_BLOG,
        "output": "json",
    }
    res = requests.post(url, params=params, files=files)
    res.raise_for_status()
    data = res.json()
    return data["tistory"]["replacer"]  # 업로드된 이미지 URL


# ── 5. 쿠팡 파트너스 링크 자동 삽입 ──────────────────────
def insert_coupang_links(content: str) -> str:
    """본문에서 키워드를 찾아 쿠팡 링크로 교체 (첫 번째 등장만)"""
    used_keywords = set()

    for keyword, link in COUPANG_KEYWORD_MAP.items():
        if keyword in content and keyword not in used_keywords:
            # 첫 번째 등장한 키워드만 링크 처리
            anchor = f'<a href="{link}" target="_blank" rel="noopener">{keyword}</a>'
            content = content.replace(keyword, anchor, 1)
            used_keywords.add(keyword)

    # 파트너스 안내 문구 추가 (법적 의무)
    disclosure = (
        '\n\n<p style="font-size:12px;color:#888;">'
        '⚠️ 이 포스팅은 쿠팡 파트너스 활동의 일환으로, '
        '이에 따른 일정액의 수수료를 제공받습니다.'
        '</p>'
    )
    return content + disclosure


# ── 6. 티스토리 포스트 수정 (이미지 + 링크 반영) ───────────
def update_tistory_post(post_id: str, title: str, content: str) -> bool:
    """기존 포스트 내용을 수정"""
    url = "https://www.tistory.com/apis/post/modify"
    params = {
        "access_token": TISTORY_TOKEN,
        "blogName": TISTORY_BLOG,
        "postId": post_id,
        "title": title,
        "content": content,
        "output": "json",
    }
    res = requests.post(url, params=params)
    res.raise_for_status()
    return res.json()["tistory"]["status"] == "200"


# ── 7. Notion 상태 업데이트 ───────────────────────────────
def update_notion_status(page_id: str, status: str):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "상태": {"select": {"name": status}},
            "처리완료시각": {"date": {"start": datetime.utcnow().isoformat() + "Z"}},
        }
    }
    res = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    res.raise_for_status()


# ── 메인 파이프라인 ────────────────────────────────────────
def process_post(page: dict):
    page_id = page["id"]
    props   = page["properties"]

    # 기본 정보 추출
    title   = props.get("제목", {}).get("title", [{}])[0].get("text", {}).get("content", "제목없음")
    post_id = props.get("TistoryPostID", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")

    print(f"\n[처리중] {title} (PostID: {post_id})")

    if not post_id:
        print("  ⚠️  TistoryPostID 없음 - 건너뜀 (Notion DB에 TistoryPostID 컬럼 필요)")
        return

    try:
        # 본문 가져오기
        content = get_notion_page_content(page_id)

        # 3. 썸네일 생성
        print("  📸 썸네일 생성중...")
        img_bytes = generate_thumbnail(title)

        # 4. 티스토리 이미지 업로드
        print("  ⬆️  이미지 업로드중...")
        img_filename = f"thumb_{int(time.time())}.png"
        img_tag = upload_image_to_tistory(img_bytes, img_filename)

        # 썸네일을 본문 최상단에 삽입
        content_with_thumb = f'<div style="text-align:center;">{img_tag}</div>\n\n{content}'

        # 5. 쿠팡 링크 삽입
        print("  🔗 쿠팡 링크 삽입중...")
        final_content = insert_coupang_links(content_with_thumb)

        # 6. 티스토리 포스트 업데이트
        print("  ✏️  포스트 업데이트중...")
        success = update_tistory_post(post_id, title, final_content)

        if success:
            # 7. Notion 상태 업데이트
            update_notion_status(page_id, "전체완료")
            print(f"  ✅ 완료: {title}")
        else:
            print(f"  ❌ 티스토리 업데이트 실패")
            update_notion_status(page_id, "오류")

    except Exception as e:
        print(f"  ❌ 오류 발생: {e}")
        update_notion_status(page_id, "오류")


def main():
    print(f"🚀 후처리 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    pending = fetch_pending_posts()
    print(f"📋 처리 대기 포스팅: {len(pending)}건")

    for page in pending:
        process_post(page)
        time.sleep(2)  # API rate limit 방지

    print("\n✅ 모든 처리 완료")


if __name__ == "__main__":
    main()
