"""
기존 Tistory 포스트에 대표 이미지만 추가하는 일회성 스크립트.
신규 발행이 아닌 수정(manage/post/{num}) 경로 사용 — 중복 발행 방지.
"""

import os
import base64
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

TISTORY_ID   = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW   = os.getenv("TISTORY_KAKAO_PASSWORD")
TISTORY_BLOG = os.getenv("TISTORY_BLOG_NAME")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY")

TARGETS = [
    (127, "카드론과 현금서비스 차이 — 신용점수와 이자 부담 비교"),
    (128, "전세 계약 갱신 전 보증보험 다시 확인해야 하는 이유"),
]


def generate_thumbnail(title: str) -> str:
    """gpt-image-1-mini로 썸네일 생성 → base64 반환"""
    prompt = (
        f"블로그 썸네일, 주제: '{title}'. "
        "고급스럽고 전문적인 일러스트, 텍스트 없음, 16:9 비율, 한국 블로그 스타일"
    )
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    payload = {"model": "gpt-image-1-mini", "prompt": prompt, "n": 1, "size": "1536x1024"}
    res = requests.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload)
    res.raise_for_status()
    return res.json()["data"][0]["b64_json"]


def save_thumb(b64: str, num: int) -> str:
    path = os.path.join(os.path.dirname(__file__), "_thumbs", f"thumb_post{num}.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return path


def find_edit_url(page, post_num: int) -> str:
    """manage/posts 목록에서 해당 포스트의 수정 URL 탐색"""
    import re as _re
    list_url = f"https://{TISTORY_BLOG}.tistory.com/manage/posts"
    page.goto(list_url, wait_until="networkidle")
    page.wait_for_timeout(1500)

    # 모든 수정 링크 href 수집
    hrefs = page.evaluate("""
        () => Array.from(document.querySelectorAll('a.btn_post[href*="/manage/post/"]'))
                   .map(a => a.href)
    """)
    print(f"  수정링크 {len(hrefs)}개 발견")
    if not hrefs:
        return ""

    # 첫 페이지에 없으면 여러 페이지를 시도할 수 있지만, 최신 글이므로 첫 페이지에 있어야 함
    # 관리 내부 ID와 공개 URL 번호가 다를 수 있으므로 각 링크를 클릭해 제목 확인 불가
    # → 대신: 링크에서 내부 ID 추출 후 가장 큰 번호(= 최신) 순 정렬
    ids = []
    for h in hrefs:
        m = _re.search(r'/manage/post/(\d+)', h)
        if m:
            ids.append((int(m.group(1)), h))
    if not ids:
        return ""

    # post_num에 해당하는 내부 ID를 직접 알 수 없으므로:
    # /127은 최신에서 N번째 글 — post_num과 내부 ID를 매핑하는 방법이 없음
    # → 타이틀로 구분: 각 edit URL에서 제목 확인 (최대 5개만 시도)
    # 단, 비효율적이므로: 가장 최근 글들(내부 ID 내림차순)에서 post_num을 추론
    # 실제로는 공개 URL /127 = tistory DB의 postId일 가능성 높음
    # → 직접 시도
    target_href = f"https://{TISTORY_BLOG}.tistory.com/manage/post/{post_num}"
    print(f"  시도: {target_href}")
    return target_href


def upload_thumbnail_to_post(page, post_num: int, thumb_path: str):
    # manage/post/{num} 직접 접근 (로그인된 상태에서)
    edit_url = f"https://{TISTORY_BLOG}.tistory.com/manage/post/{post_num}"
    print(f"  이동: {edit_url}")
    page.goto(edit_url, wait_until="networkidle")
    page.wait_for_timeout(2000)
    print(f"  최종 URL: {page.url}")
    page.screenshot(path=os.path.join(os.path.dirname(__file__), f"debug_edit_{post_num}.png"))

    # 실제 에디터 페이지인지 확인 (제목 필드 존재 여부)
    has_editor = page.evaluate("""
        () => {
            return !!(document.querySelector('textarea#title, input#title, [placeholder*="제목"]')
                   || (typeof tinymce !== 'undefined' && tinymce.activeEditor));
        }
    """)
    if not has_editor:
        print(f"  ⚠️  에디터 미로드 — URL 확인 필요")
        return

    # TinyMCE 로드 대기
    for _ in range(15):
        loaded = page.evaluate("() => typeof tinymce !== 'undefined' && !!tinymce.activeEditor")
        if loaded:
            break
        page.wait_for_timeout(1000)
    page.wait_for_timeout(1000)
    print("  에디터 준비")

    # 발행 패널 열기
    result = page.evaluate("""
        () => {
            const btns = Array.from(document.querySelectorAll('button'));
            const btn = btns.find(b => b.textContent.trim() === '완료');
            if (btn) { btn.click(); return '클릭'; }
            return '없음: ' + btns.map(b => b.textContent.trim()).filter(t => t).slice(0, 10).join(' | ');
        }
    """)
    print(f"  완료 버튼: {result}")
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(os.path.dirname(__file__), f"debug_panel_{post_num}.png"))

    # 대표이미지 업로드
    file_info = page.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input[type="file"]');
            return inputs.length + ' ea, accept: ' + Array.from(inputs).map(i => i.accept).join(', ');
        }
    """)
    print(f"  file inputs: {file_info}")
    page.locator('input[type="file"][accept="image/*"]').first.set_input_files(
        thumb_path, timeout=10000
    )
    page.wait_for_timeout(2000)
    print("  이미지 업로드 완료")

    # 공개 라디오 클릭
    page.evaluate("""
        () => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while (node = walker.nextNode()) {
                if (node.textContent.trim() === '공개') {
                    const el = node.parentElement;
                    if (el && el.offsetParent !== null) { el.click(); return; }
                }
            }
        }
    """)
    page.wait_for_timeout(1000)

    # 공개 발행
    page.get_by_role("button", name="공개 발행").click(timeout=5000)
    page.wait_for_timeout(3000)
    print(f"  /{ post_num } 완료")


def main():
    # 1단계: 썸네일 생성
    thumb_paths = {}
    for num, title in TARGETS:
        cache = os.path.join(os.path.dirname(__file__), "_thumbs", f"thumb_post{num}.png")
        if os.path.exists(cache):
            print(f"[/{ num }] 캐시 사용: {cache}")
            thumb_paths[num] = cache
        else:
            print(f"[/{ num }] 썸네일 생성중...")
            b64 = generate_thumbnail(title)
            thumb_paths[num] = save_thumb(b64, num)
            print(f"  저장: {thumb_paths[num]}")

    # 2단계: Tistory에 업로드
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=400)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="ko-KR")
        page = context.new_page()

        # 로그인
        print("\n로그인중...")
        page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
        page.click('a.btn_login.link_kakao_id')
        page.wait_for_load_state("networkidle")
        page.fill('input[name="loginId"]', TISTORY_ID)
        page.fill('input[name="password"]', TISTORY_PW)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        print(f"  로그인 후 URL: {page.url}")

        # 블로그 관리 도메인 세션 수립 — 반드시 먼저 방문해야 쿠키가 j2gblog.tistory.com에 세팅됨
        page.goto(f"https://{TISTORY_BLOG}.tistory.com/manage", wait_until="networkidle")
        page.wait_for_timeout(2000)
        print(f"  관리 페이지 URL: {page.url}")
        page.screenshot(path=os.path.join(os.path.dirname(__file__), "debug_login.png"))
        print("로그인 완료\n")

        for num, _ in TARGETS:
            print(f"[/{num}] 처리중...")
            upload_thumbnail_to_post(page, num, thumb_paths[num])

        browser.close()

    print("\n완료. OG 이미지 URL 수집 시작...")
    for num, _ in TARGETS:
        url = f"https://{TISTORY_BLOG}.tistory.com/{num}"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        import re
        m = re.search(r'property="og:image"\s+content="([^"]+)"', r.text)
        if not m:
            m = re.search(r'content="([^"]+)"\s+property="og:image"', r.text)
        og = m.group(1) if m else "NOT FOUND"
        print(f"/{num} OG: {og}")


if __name__ == "__main__":
    main()
