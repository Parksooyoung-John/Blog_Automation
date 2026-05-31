"""
티스토리 Playwright 자동 포스팅 스크립트
- 티스토리 Open API 종료(2024.02) 대응
- Playwright로 브라우저 직접 제어
- Notion DB → 티스토리 자동 발행
- DALL-E 썸네일 생성 + 쿠팡 링크 삽입

설치:
    pip install playwright python-dotenv requests --break-system-packages
    playwright install chromium
"""

import os
import re
import time
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

load_dotenv()

# ── 환경변수 ──────────────────────────────────────────
TISTORY_ID      = os.getenv("TISTORY_KAKAO_EMAIL")     # 카카오 로그인 이메일
TISTORY_PW      = os.getenv("TISTORY_KAKAO_PASSWORD")  # 카카오 로그인 비밀번호
TISTORY_BLOG    = os.getenv("TISTORY_BLOG_NAME")       # 블로그명 (xxx.tistory.com 의 xxx)
NOTION_KEY      = os.getenv("NOTION_API_KEY")
NOTION_DB_ID    = os.getenv("NOTION_DATABASE_ID")
OPENAI_KEY      = os.getenv("OPENAI_API_KEY")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# ── 쿠팡 파트너스 키워드 맵 ────────────────────────────
COUPANG_KEYWORD_MAP = {
    "심리학": "https://link.coupang.com/re/AFFILCODE?itemId=ITEM1",
    "역사": "https://link.coupang.com/re/AFFILCODE?itemId=ITEM2",
    "인지편향": "https://link.coupang.com/re/AFFILCODE?itemId=ITEM3",
}

# ═══════════════════════════════════════════════════════
# NOTION 관련 함수
# ═══════════════════════════════════════════════════════

def fetch_pending_posts() -> list:
    """Notion DB에서 '발행대기' 상태 항목 조회"""
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    payload = {
        "filter": {
            "property": "상태",
            "select": {"equals": "발행대기"}
        },
        "sorts": [{"property": "날짜", "direction": "ascending"}]
    }
    res = requests.post(url, headers=NOTION_HEADERS, json=payload)
    res.raise_for_status()
    return res.json().get("results", [])


def _generate_title_with_gpt(text: str) -> str:
    """GPT로 짧고 캐치한 블로그 제목 생성 (최대 25자)"""
    if not OPENAI_KEY or not OPENAI_KEY.startswith("sk-proj"):
        return ""
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "당신은 블로그 제목 전문가입니다. "
                        "주어진 내용을 바탕으로 독자의 클릭을 유도하는 "
                        "짧고 임팩트 있는 한국어 블로그 제목을 작성하세요. "
                        "규칙: 20자 이내, 숫자/의문문/감탄 활용 가능, "
                        "제목만 출력 (따옴표 없이)"
                    )
                },
                {
                    "role": "user",
                    "content": f"다음 내용의 블로그 제목을 작성해주세요:\n\n{text}"
                }
            ],
            "max_tokens": 60,
            "temperature": 0.8,
        }
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=payload
        )
        res.raise_for_status()
        title = res.json()["choices"][0]["message"]["content"].strip()
        # 따옴표 제거 및 20자 제한
        title = title.strip('"\'').strip()[:25]
        return title
    except Exception as e:
        print(f"  ⚠️  GPT 제목 생성 실패 (fallback 사용): {e}")
        return ""


def get_notion_page_blocks(page_id: str) -> str:
    """Notion 페이지 블록에서 전체 텍스트 추출 — 페이지네이션으로 전체 블록 수집"""
    texts = []
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    while url:
        res = requests.get(url, headers=NOTION_HEADERS)
        if res.status_code != 200:
            break
        data = res.json()
        for block in data.get("results", []):
            btype = block.get("type", "")
            bdata = block.get(btype, {})
            rich  = bdata.get("rich_text", [])
            text  = "".join(rt.get("plain_text", "") for rt in rich)
            if text.strip():
                texts.append(text.strip())
        if data.get("has_more") and data.get("next_cursor"):
            url = (
                f"https://api.notion.com/v1/blocks/{page_id}/children"
                f"?page_size=100&start_cursor={data['next_cursor']}"
            )
        else:
            url = None
    return "\n".join(texts)


def _strip_base64_images(html: str) -> str:
    """<figure> 블록 내 base64 data URI 이미지 제거.
    6MB+ base64는 Tistory 제출 크기 한도를 초과해 publish가 실패함.
    Pexels URL 이미지는 짧으므로 보존됨.
    """
    FIGURE_START = '<figure'
    FIGURE_END = '</figure>'
    DATA_URI = 'data:image/'
    parts: list[str] = []
    pos = 0
    while True:
        fig_s = html.find(FIGURE_START, pos)
        if fig_s == -1:
            parts.append(html[pos:])
            break
        fig_e = html.find(FIGURE_END, fig_s)
        if fig_e == -1:
            parts.append(html[pos:])
            break
        fig_block = html[fig_s: fig_e + len(FIGURE_END)]
        if DATA_URI in fig_block:
            parts.append(html[pos:fig_s])       # base64 figure 제거
        else:
            parts.append(html[pos:fig_e + len(FIGURE_END)])  # URL 이미지 유지
        pos = fig_e + len(FIGURE_END)
    result = ''.join(parts)
    if len(result) < len(html):
        removed = len(html) - len(result)
        print(f"  ℹ️  base64 이미지 제거: {removed // 1024}KB 감소")
    return result


def get_script_content(page: dict) -> tuple:
    """스크립트 내용 추출 후 (제목, HTML본문) 반환

    [수정] 3가지 문제 해결:
    1. 제목: GPT 생성 (실패시 키워드 기반 fallback)
    2. 본문: 문단 간격 CSS 추가
    3. 끊김 방지: property(2000자 제한) + page blocks 모두 읽어 합치기
    """
    props   = page.get("properties", {})
    page_id = page.get("id", "")

    # ① property에서 읽기 (최대 2000자)
    script_rich = props.get("스크립트", {}).get("rich_text", [])
    prop_text   = "".join(rt.get("plain_text", "") for rt in script_rich)

    # ② 페이지 blocks에서 읽기 (제한 없음) — Make.com이 body에 저장하는 경우
    block_text = get_notion_page_blocks(page_id)

    # ③ 더 긴 쪽 사용 (blocks가 있으면 blocks 우선)
    raw_text = block_text if len(block_text) > len(prop_text) else prop_text

    if not raw_text:
        return "제목없음", "<p>내용 없음</p>"

    # 04_notion_upload.py가 저장한 HTML: 이름 프로퍼티에 제목이 이미 있으므로 GPT 생성 스킵
    stripped = raw_text.strip()
    if stripped.startswith('<'):
        return "", _strip_base64_images(stripped)

    # ─── 제목 생성 (Make.com 원문 텍스트 경로) ───────────────
    auto_title = _generate_title_with_gpt(raw_text[:800])
    if not auto_title:
        # fallback: 인사말·짧은 문장 건너뛰고 핵심 주제 문장 추출
        skip_starts = ('안녕하세요', '안녕', '여러분', '오늘', '이번', '반갑', '함께', '먼저')
        lines_all   = [l.strip() for l in raw_text.split("\n") if l.strip()]
        auto_title  = "제목없음"
        for line in lines_all:
            if len(line) >= 15 and not any(line.startswith(p) for p in skip_starts):
                # 쉼표/마침표 이전까지 (자연스러운 끊기)
                import re as _re
                part = _re.split(r'[,\.。]', line)[0].strip()
                auto_title = part[:25] if len(part) >= 8 else line[:25]
                break
        if auto_title == "제목없음" and len(raw_text) > 0:
            # 최후 fallback: 전체 텍스트 중간에서 키워드 찾기
            auto_title = raw_text.replace('\n', ' ').strip()[:20]

    # Make.com 원문 텍스트: 문단 간격 CSS 포함, 빈줄은 <br> 처리
    html_parts = ['<div style="line-height:1.9; font-size:16px;">']
    lines = raw_text.split("\n")
    for line in lines:
        line = line.strip()
        if line:
            html_parts.append(
                f'<p style="margin-bottom:18px;">{line}</p>'
            )
        else:
            html_parts.append('<br>')
    html_parts.append('</div>')

    return auto_title, "\n".join(html_parts)


def update_notion_status(page_id: str, status: str, post_url: str = ""):
    """Notion 페이지 상태 업데이트"""
    props = {
        "상태": {"select": {"name": status}},
        "처리완료시각": {"date": {"start": datetime.utcnow().isoformat() + "Z"}},
    }
    if post_url:
        props["발행URL"] = {"url": post_url}

    url = f"https://api.notion.com/v1/pages/{page_id}"
    requests.patch(url, headers=NOTION_HEADERS, json={"properties": props})


# ═══════════════════════════════════════════════════════
# 이미지 / 콘텐츠 처리 함수
# ═══════════════════════════════════════════════════════

def generate_thumbnail_base64(title: str) -> str:
    """DALL-E로 썸네일 생성 후 base64 반환"""
    prompt = (
        f"블로그 썸네일, 주제: '{title}'. "
        "고급스럽고 전문적인 일러스트, 텍스트 없음, 16:9 비율, "
        "한국 블로그 스타일"
    )
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-image-1",
        "prompt": prompt,
        "n": 1,
        "size": "1536x1024",
    }
    res = requests.post("https://api.openai.com/v1/images/generations",
                        headers=headers, json=payload)
    res.raise_for_status()
    return res.json()["data"][0]["b64_json"]


def save_thumbnail_temp(b64_data: str, title: str) -> str:
    """base64 이미지를 임시 파일로 저장 후 경로 반환"""
    filename = f"thumb_{int(time.time())}.png"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(b64_data))
    return filepath


def insert_coupang_links(html: str) -> str:
    """HTML 본문에 쿠팡 링크 삽입 (키워드당 첫 등장만)"""
    used = set()
    for keyword, link in COUPANG_KEYWORD_MAP.items():
        if keyword in html and keyword not in used:
            anchor = f'<a href="{link}" target="_blank" rel="noopener sponsored">{keyword}</a>'
            html = html.replace(keyword, anchor, 1)
            used.add(keyword)

    disclosure = (
        '\n<p style="font-size:12px;color:#999;margin-top:40px;">'
        '이 포스팅은 쿠팡 파트너스 활동의 일환으로 수수료를 제공받을 수 있습니다.'
        '</p>'
    )
    return html + disclosure


# ═══════════════════════════════════════════════════════
# PLAYWRIGHT 티스토리 자동화
# ═══════════════════════════════════════════════════════

def login_tistory(page: Page):
    """카카오 계정으로 티스토리 로그인"""
    print("  🔐 티스토리 로그인중...")
    page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")

    # 카카오 로그인 버튼 클릭
    page.click('a.btn_login.link_kakao_id')
    page.wait_for_load_state("networkidle")

    # 카카오 이메일/비밀번호 입력
    page.fill('input[name="loginId"]', TISTORY_ID)
    page.fill('input[name="password"]', TISTORY_PW)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    # 로그인 성공 확인
    if "tistory.com" in page.url:
        print("  ✅ 로그인 완료")
    else:
        raise Exception("로그인 실패 - 이메일/비밀번호 확인")


def post_to_tistory(page: Page, title: str, html_content: str,
                    tags: list, category_name: str = "",
                    thumb_path: str = "") -> str:
    """티스토리에 글 작성 후 발행된 URL 반환"""

    write_url = f"https://{TISTORY_BLOG}.tistory.com/manage/newpost"
    print(f"  ✏️  글 작성 페이지 이동...")
    page.goto(write_url, wait_until="networkidle")
    page.wait_for_timeout(2000)

    # ── 제목 입력 ──────────────────────────────────────
    title_selector = 'textarea#title, input#title, [placeholder*="제목"]'
    page.wait_for_selector(title_selector, timeout=10000)
    page.fill(title_selector, title)
    print(f"  📝 제목 입력: {title}")

    # 대표이미지는 발행 패널 안에 있음 → 패널 오픈 후 업로드

    # ── 본문 입력 (TinyMCE 에디터) ────────────────────────
    page.wait_for_timeout(2000)
    try:
        # TinyMCE API로 직접 내용 삽입 + change 이벤트 발생
        escaped = html_content.replace("\\", "\\\\").replace("`", "\\`")
        inserted = page.evaluate(f"""
            () => {{
                // TinyMCE 방식
                if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {{
                    tinymce.activeEditor.setContent(`{escaped}`);
                    tinymce.activeEditor.fire('change');  // 변경사항 강제 등록
                    tinymce.activeEditor.save();          // 원본 textarea에 동기화
                    return 'tinymce';
                }}
                // iframe 내부 직접 접근
                const iframe = document.querySelector('iframe.tox-edit-area__iframe');
                if (iframe) {{
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    const body = doc.querySelector('body');
                    if (body) {{
                        body.innerHTML = `{escaped}`;
                        body.dispatchEvent(new Event('input', {{bubbles: true}}));
                        return 'iframe';
                    }}
                }}
                // contenteditable fallback
                const editable = document.querySelector('[contenteditable="true"]');
                if (editable) {{
                    editable.innerHTML = `{escaped}`;
                    editable.dispatchEvent(new Event('input', {{bubbles: true}}));
                    return 'contenteditable';
                }}
                return null;
            }}
        """)
        page.wait_for_timeout(1500)  # 내용 반영 대기
        print(f"  📝 본문 입력 완료 (방식: {inserted})")
    except Exception as e:
        print(f"  ⚠️  본문 입력 오류: {e}")

    page.wait_for_timeout(1000)

    # ── 태그 입력 (에디터 하단, 완료 클릭 전) ─────────────
    # locator 사용: DOM 재렌더링 후에도 lazy-evaluate로 안전하게 동작
    if tags:
        try:
            tag_loc = page.locator(
                'input[name="tag"], input[placeholder*="태그입력"], input[placeholder*="태그"]'
            ).first
            tag_loc.wait_for(state="visible", timeout=5000)
            for tag in tags:
                tag_loc.click()
                page.keyboard.type(tag)
                page.keyboard.press("Enter")
                page.wait_for_timeout(300)
            print(f"  🏷️  태그 입력 완료: {', '.join(tags)}")
        except Exception as e:
            print(f"  ⚠️  태그 입력 스킵: {e}")

    # ── 발행 패널 열기 ("완료" 버튼 클릭) ──────────────────
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(os.path.dirname(__file__), "debug_before_publish.png"))

    try:
        page.get_by_role("button", name="완료").click()
    except Exception:
        # fallback: 텍스트로 버튼 탐색
        page.locator("button", has_text="완료").first.click()
    print(f"  🚀 '완료' 클릭 → 발행 패널 대기...")
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(os.path.dirname(__file__), "debug_panel.png"))

    # ── 발행 패널: 대표이미지 업로드 ──────────────────────
    if thumb_path and os.path.exists(thumb_path):
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.locator("text=대표이미지 추가").click(timeout=3000)
            fc_info.value.set_files(thumb_path)
            page.wait_for_timeout(2000)
            print("  🖼️  대표이미지 업로드 완료")
        except Exception as e:
            print(f"  ⚠️  대표이미지 업로드 스킵: {e}")

    # ── 발행 패널: 카테고리(홈주제) 선택 ──────────────────
    # TinyMCE의 disabled "선택 안 함" 버튼과 구분: not([disabled]) 필터 적용
    if category_name:
        try:
            page.locator("button:not([disabled])").filter(
                has_text="선택 안 함"
            ).first.click(timeout=3000)
            page.wait_for_timeout(600)
            try:
                page.get_by_role("button", name=category_name).click(timeout=3000)
            except Exception:
                page.locator(f"text={category_name}").first.click(timeout=3000)
            print(f"  📁 카테고리: {category_name}")
        except Exception as e:
            print(f"  ⚠️  카테고리 선택 스킵: {e}")
        page.wait_for_timeout(500)

    # ── 발행 패널에서 URL 추출 ────────────────────────────
    # URL 필드 = dt>dd (prefix 텍스트) + dd>input.value (editable slug)
    panel_url = page.evaluate("""
        () => {
            for (const dt of document.querySelectorAll('dt')) {
                if (dt.textContent.trim() === 'URL') {
                    const dd = dt.nextElementSibling;
                    if (!dd) return null;
                    const prefix = dd.textContent.trim();
                    const inp = dd.querySelector('input[type="text"]');
                    const slug = inp ? inp.value.trim() : '';
                    return slug ? prefix.replace(/\\/$/, '') + '/' + slug : prefix;
                }
            }
            return null;
        }
    """)
    if panel_url and 'tistory.com' in (panel_url or ''):
        print(f"  🔗 발행 URL: {panel_url}")
    else:
        panel_url = None

    # ── 발행 패널: 공개 라디오 ─────────────────────────────
    # React 커스텀 라디오: visible 텍스트 노드 "공개"의 부모 요소를 클릭
    clicked_el = page.evaluate("""
        () => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while (node = walker.nextNode()) {
                if (node.textContent.trim() === '공개') {
                    const el = node.parentElement;
                    if (el && el.offsetParent !== null) {
                        el.click();
                        return el.tagName + ':' + el.className;
                    }
                }
            }
            return null;
        }
    """)
    print(f"  🔘 공개 설정: {clicked_el or '실패'}")
    page.wait_for_timeout(1000)

    # ── 최종 발행 (공개 클릭 후 버튼이 "공개 발행"으로 변경됨) ──
    try:
        page.get_by_role("button", name="공개 발행").click(timeout=5000)
        print("  ✅ 최종 발행: '공개 발행' 클릭")
    except Exception as e:
        all_btns = page.locator("button").all_inner_texts()
        print(f"  ⚠️  발행 버튼 실패 — 버튼목록: {all_btns}")
        raise Exception(f"공개 발행 버튼 없음: {e}")

    page.wait_for_timeout(4000)
    page.screenshot(path=os.path.join(os.path.dirname(__file__), "debug_after_publish.png"))

    # ── 발행된 URL 반환 (패널 URL 우선, 폴백: 현재 탭 URL) ─
    page.wait_for_timeout(2000)
    final_url = panel_url or page.url
    print(f"  ✅ 발행 완료: {final_url}")
    return final_url


# ═══════════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════════

def process_all():
    print(f"\n🚀 자동 포스팅 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    pending = fetch_pending_posts()
    if not pending:
        print("📋 발행 대기 중인 포스팅 없음")
        return

    print(f"📋 발행 대기: {len(pending)}건")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,   # 처음에는 False로 두고 동작 확인 후 True로 변경
            slow_mo=500,      # 각 동작 간 0.5초 딜레이 (안정성)
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
        page = context.new_page()

        # 로그인 (세션 유지)
        login_tistory(page)

        for notion_page in pending:
            page_id = notion_page["id"]
            props   = notion_page["properties"]

            # 현재 DB 컬럼: 이름(Title) | 날짜(Date) | 스크립트(Text)
            title_list = props.get("이름", {}).get("title", [])
            title = title_list[0].get("text", {}).get("content", "제목없음") if title_list else "제목없음"
            tags  = [t["name"] for t in props.get("태그", {}).get("multi_select", [])]
            category = (props.get("카테고리", {}).get("select", {}) or {}).get("name", "")

            print(f"\n[{title}] 처리 시작...")

            # Notion 상태 → 처리중
            update_notion_status(page_id, "처리중")

            try:
                # 1. 본문 가져오기 ('스크립트' 컬럼에서 추출 → 제목+HTML 반환)
                auto_title, html_body = get_script_content(notion_page)
                # Notion 행 이름이 의미없는 경우 스크립트 첫 문장을 제목으로 사용
                if title in ("스크립트", "제목없음", ""):
                    title = auto_title
                    print(f"  🏷️  제목 자동 추출: {title}")

                # 2. 썸네일 생성
                thumb_path = ""
                if OPENAI_KEY:
                    print("  📸 썸네일 생성중 (DALL-E)...")
                    try:
                        b64 = generate_thumbnail_base64(title)
                        thumb_path = save_thumbnail_temp(b64, title)
                    except Exception as e:
                        print(f"  ⚠️  썸네일 생성 실패 (스킵): {e}")

                # 3. 쿠팡 링크 삽입
                final_html = insert_coupang_links(html_body)

                # 4. 티스토리 발행
                post_url = post_to_tistory(
                    page=page,
                    title=title,
                    html_content=final_html,
                    tags=tags,
                    category_name=category,
                    thumb_path=thumb_path,
                )

                # 5. Notion 상태 → 발행완료
                update_notion_status(page_id, "발행완료", post_url)

                # 임시 썸네일 파일 삭제
                if thumb_path and os.path.exists(thumb_path):
                    os.remove(thumb_path)

                print(f"  ✅ [{title}] 완료")
                time.sleep(3)  # 연속 발행 시 딜레이

            except Exception as e:
                print(f"  ❌ 오류: {e}")
                update_notion_status(page_id, "오류")

        browser.close()

    print("\n✅ 전체 처리 완료")


if __name__ == "__main__":
    process_all()
