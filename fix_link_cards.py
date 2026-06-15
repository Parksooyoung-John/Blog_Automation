"""
발행된 ETF 포스트 2개의 '함께 읽으면 좋은 글' 카드 이미지 수정
- 발행된 포스트 URL → 관리자 편집 링크로 포스트 ID 획득
- TinyMCE에서 img src 교체 후 재발행
"""

import os, re, time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page

load_dotenv()

TISTORY_EMAIL = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW    = os.getenv("TISTORY_KAKAO_PASSWORD")
BLOG_NAME     = os.getenv("TISTORY_BLOG_NAME", "j2gblog")

THUMB = {
    "월배당ETF": "https://img1.daumcdn.net/thumb/R800x0/?scode=mtistory2&fname=https%3A%2F%2Fblog.kakaocdn.net%2Fdna%2Fr8r7D%2FdJMcabdk99T%2FAAAAAAAAAAAAAAAAAAAAAHUxEFP9uB4dK1yDO1laR_KSDCbNqJrHDmO8NXYcCnlw%2Fimg.png%3Fcredential%3DyqXZFxpELC7KVnFOS48ylbz2pIh7yKj8%26expires%3D1782831599%26allow_ip%3D%26allow_referer%3D%26signature%3DtbxroUFA05QZ4CSXq98rQ4%252Bt5VE%253D",
    "계좌별ETF세금": "https://img1.daumcdn.net/thumb/R800x0/?scode=mtistory2&fname=https%3A%2F%2Fblog.kakaocdn.net%2Fdna%2F0F5CX%2FdJMcacKbGXU%2FAAAAAAAAAAAAAAAAAAAAAOkrz3fzL7mOOQf40UrFQOx7_gB99jbqxv4JknlmHZH-%2Fimg.png%3Fcredential%3DyqXZFxpELC7KVnFOS48ylbz2pIh7yKj8%26expires%3D1782831599%26allow_ip%3D%26allow_referer%3D%26signature%3DtPK8583neucJt2A98nb9Rk4%252FKpk%253D",
    "밸류업ETF": "https://img1.daumcdn.net/thumb/R800x0/?scode=mtistory2&fname=https%3A%2F%2Fblog.kakaocdn.net%2Fdna%2FL0Qse%2FdJMcacciYdZ%2FAAAAAAAAAAAAAAAAAAAAAIiFsZB8nZKpHv4mvfRXBjCpA7foJ7RvGGKtEv8YSMSm%2Fimg.png%3Fcredential%3DyqXZFxpELC7KVnFOS48ylbz2pIh7yKj8%26expires%3D1782831599%26allow_ip%3D%26allow_referer%3D%26signature%3D5ZzTwoKATPhqVfYWUHcVG02H2Sc%253D",
    "ISA14": "https://img1.daumcdn.net/thumb/R800x0/?scode=mtistory2&fname=https%3A%2F%2Fblog.kakaocdn.net%2Fdna%2FEzdyU%2FdJMcafUmaG0%2FAAAAAAAAAAAAAAAAAAAAAJ4r7JKbzzHXfTJ3-zzEpkzXHEX4-MF98BCe1TV4dXx3%2Fimg.png%3Fcredential%3DyqXZFxpELC7KVnFOS48ylbz2pIh7yKj8%26expires%3D1782831599%26allow_ip%3D%26allow_referer%3D%26signature%3Dc96rIvNJFG%252BYXtxoYqOap25JMMA%253D",
}

# 발행 URL + 카드 수정 정보
POSTS_TO_FIX = [
    {
        "label": "밸류업 ETF",
        "edit_url": "https://j2gblog.tistory.com/manage/post/64",
        "cards": [
            ("월배당", "월배당ETF"),
            ("계좌별", "계좌별ETF세금"),
            ("/14",   "ISA14"),
        ]
    },
    {
        "label": "단일종목 레버리지 ETF",
        "edit_url": "https://j2gblog.tistory.com/manage/post/63",
        "cards": [
            ("계좌별", "계좌별ETF세금"),
            ("월배당", "월배당ETF"),
            ("/14",   "ISA14"),
        ]
    },
]


def kakao_login(page: Page):
    page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
    page.click("a.btn_login.link_kakao_id")
    page.wait_for_load_state("networkidle")
    page.fill('input[name="loginId"]', TISTORY_EMAIL)
    page.fill('input[name="password"]', TISTORY_PW)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    print(f"  ✅ 로그인 완료 (현재 URL: {page.url[:60]})")


def get_edit_url_from_post(page: Page, post_url: str) -> str | None:
    """발행된 포스트 URL에서 관리자 편집 URL 추출"""
    page.goto(post_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    html = page.content()
    # 편집 링크: /manage/post/NNNN
    m = re.search(r'href="(/manage/post/(\d+))"', html)
    if m:
        post_id = m.group(2)
        edit_url = f"https://{BLOG_NAME}.tistory.com/manage/post/{post_id}"
        print(f"  포스트 ID: {post_id}")
        return edit_url

    # 다른 패턴 시도
    m2 = re.search(r'/manage/post/(\d+)', html)
    if m2:
        edit_url = f"https://{BLOG_NAME}.tistory.com/manage/post/{m2.group(1)}"
        print(f"  포스트 ID (alt): {m2.group(1)}")
        return edit_url

    # 페이지에서 수동으로 편집 버튼 확인
    edit_links = page.locator("a[href*='/manage/post/']").all()
    if edit_links:
        href = edit_links[0].get_attribute("href")
        edit_url = f"https://{BLOG_NAME}.tistory.com{href}" if href.startswith("/") else href
        print(f"  편집 링크 발견: {edit_url}")
        return edit_url

    print(f"  ⚠️  편집 링크를 찾을 수 없음. 현재 URL: {page.url}")
    print(f"  페이지 링크 샘플: {[a.get_attribute('href') for a in page.locator('a').all()[:10]]}")
    return None


def get_edit_url_from_manage(page: Page, keyword: str) -> str | None:
    """관리 페이지를 스크롤하며 포스트 ID 탐색"""
    page.goto(f"https://{BLOG_NAME}.tistory.com/manage/posts", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # JS로 DOM 탐색
    post_links = page.evaluate("""
        () => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            return links
                .map(a => a.href)
                .filter(h => h.includes('/manage/post/'));
        }
    """)
    print(f"  JS로 찾은 편집 링크: {post_links[:10]}")

    if not post_links:
        # 페이지 스크린샷 저장해서 디버깅
        page.screenshot(path="debug_manage.png")
        print("  스크린샷 저장: debug_manage.png")
        return None

    # 각 링크의 포스트 제목 확인
    for link in post_links[:15]:
        m = re.search(r'/manage/post/(\d+)', link)
        if not m:
            continue
        post_id = m.group(1)
        edit_url = f"https://{BLOG_NAME}.tistory.com/manage/post/{post_id}"
        page.goto(edit_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        title = ""
        for sel in ["#post-title-inp", 'input[name="title"]', "#title", 'input[placeholder*="제목"]']:
            try:
                el = page.locator(sel).first
                if el.count():
                    title = el.input_value()
                    if title:
                        break
            except:
                pass
        print(f"    ID {post_id}: '{title[:40]}'")
        if keyword in title:
            return edit_url

    return None


def apply_card_fix(page: Page, edit_url: str, cards: list, label: str):
    """편집 페이지에서 카드 img src 교체 후 재발행"""
    page.goto(edit_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)  # TinyMCE 초기화 대기
    print(f"  현재 URL: {page.url[:80]}")

    # TinyMCE 로드 대기 (최대 20초)
    tinymce_ready = False
    for _ in range(40):
        try:
            ready = page.evaluate("() => typeof tinymce !== 'undefined' && !!tinymce.activeEditor")
            if ready:
                tinymce_ready = True
                break
        except Exception:
            pass
        page.wait_for_timeout(500)

    if not tinymce_ready:
        print(f"  ❌ TinyMCE 로드 실패 ({label})")
        page.screenshot(path=f"debug_edit_{label[:5]}.png")
        return

    html = page.evaluate("() => tinymce.activeEditor.getContent()")
    if not html:
        print(f"  ❌ TinyMCE 콘텐츠 없음 ({label})")
        return

    print(f"  HTML 길이: {len(html)}자")
    modified = html

    for href_pattern, thumb_key in cards:
        correct_thumb = THUMB[thumb_key]

        def make_replacer(thumb):
            def replacer(m):
                return re.sub(
                    r'(<img\b[^>]*\bsrc=")[^"]*(")',
                    lambda im: im.group(1) + thumb + im.group(2),
                    m.group(0),
                    count=1
                )
            return replacer

        pattern = r'<a\b[^>]*href="[^"]*' + re.escape(href_pattern) + r'[^"]*"[^>]*>[\s\S]*?</a>'
        new_html = re.sub(pattern, make_replacer(correct_thumb), modified, flags=re.DOTALL)
        if new_html != modified:
            print(f"  ✅ 교체: '{href_pattern}' → {thumb_key}")
        else:
            print(f"  ⚠️  미매칭: '{href_pattern}'")
        modified = new_html

    if modified == html:
        print(f"  ❌ 변경 없음")
        return

    page.evaluate("""
        (html) => {
            tinymce.activeEditor.setContent(html);
            tinymce.activeEditor.fire('change');
            tinymce.activeEditor.save();
        }
    """, modified)
    page.wait_for_timeout(1500)
    print(f"  ✅ HTML 교체 완료")

    # 완료 버튼
    try:
        page.get_by_role("button", name="완료").click()
    except Exception:
        page.locator("button").filter(has_text="완료").first.click()
    page.wait_for_timeout(2500)

    # 공개 설정
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
    page.wait_for_timeout(800)

    # 공개 발행
    pub_btn = page.get_by_role("button", name="공개 발행")
    if pub_btn.count():
        pub_btn.click()
        page.wait_for_timeout(3000)
        print(f"  ✅ 재발행 완료 ({label})")
    else:
        print(f"  ⚠️  '공개 발행' 버튼 없음")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        print("🔐 로그인 중...")
        kakao_login(page)

        for post_info in POSTS_TO_FIX:
            label = post_info["label"]
            edit_url = post_info["edit_url"]
            print(f"\n[{label}] 처리 시작... → {edit_url}")
            apply_card_fix(page, edit_url, post_info["cards"], label)
            time.sleep(2)

        print("\n✅ 전체 완료")
        input("Enter 키를 누르면 닫힙니다...")
        browser.close()


if __name__ == "__main__":
    main()
