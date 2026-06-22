"""
Tistory 포스트 일괄 수정 유틸
- 109, 110 삭제 (중복 주제)
- 107, 108 본문 계층 여백 재적용 (hierarchical spacers)
"""

import os, importlib.util
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BLOG = os.getenv("TISTORY_BLOG_NAME")
TISTORY_ID = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW = os.getenv("TISTORY_KAKAO_PASSWORD")

# parse_blog_post 임포트 (04_notion_upload.py의 __main__ guard 덕분에 안전)
_spec = importlib.util.spec_from_file_location(
    "notion_upload", Path(__file__).parent / "04_notion_upload.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
parse_blog_post = _mod.parse_blog_post

DELETE_POST_NUMS = [109, 110]

EDIT_POSTS = [
    (107, Path(__file__).parent / "_workspace" / "blog_107_퇴직연금.md"),
    (108, Path(__file__).parent / "_workspace" / "blog_108_기초연금.md"),
]


def login(page):
    page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
    page.click("a.btn_login.link_kakao_id")
    page.wait_for_load_state("networkidle")
    page.fill('input[name="loginId"]', TISTORY_ID)
    page.fill('input[name="password"]', TISTORY_PW)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    print("✅ 로그인 완료")


def goto_manage_posts(page):
    page.goto(f"https://{BLOG}.tistory.com/manage/posts/", wait_until="networkidle")
    page.wait_for_timeout(2000)


def find_manage_url(page, post_num: int, url_type: str = "edit") -> str | None:
    """manage/posts에서 공개 URL /{post_num} 포스트의 편집/삭제 버튼을 찾아 반환.
    url_type='edit': 수정 href, url_type='del': 삭제 버튼 존재 여부
    """
    return page.evaluate("""
        ([postNum, urlType]) => {
            const pattern = new RegExp('\\/' + postNum + '(?:[?#]|$)');
            const allLinks = document.querySelectorAll('a');
            for (const link of allLinks) {
                if (link.href && pattern.test(link.href) && !link.href.includes('/manage/')) {
                    const row = link.closest('li') || link.closest('tr');
                    if (!row) continue;
                    if (urlType === 'edit') {
                        const editLink = row.querySelector('a[href*="/manage/post/"]');
                        return editLink ? editLink.href : null;
                    } else {
                        const delBtn = row.querySelector('a.btn_post[href="#"]');
                        return delBtn ? 'found' : null;
                    }
                }
            }
            return null;
        }
    """, [post_num, url_type])


def delete_post(page, post_num: int):
    """공개 URL /{post_num} 포스트 삭제"""
    print(f"\n[삭제] 포스트 /{post_num}")
    goto_manage_posts(page)

    # dialog 핸들러 먼저 등록 (native confirm)
    page.once("dialog", lambda d: d.accept())

    deleted = page.evaluate("""
        (postNum) => {
            const pattern = new RegExp('\\/' + postNum + '(?:[?#]|$)');
            const allLinks = document.querySelectorAll('a');
            for (const link of allLinks) {
                if (link.href && pattern.test(link.href) && !link.href.includes('/manage/')) {
                    const row = link.closest('li') || link.closest('tr');
                    if (!row) continue;
                    const delBtn = row.querySelector('a.btn_post[href="#"]');
                    if (delBtn) { delBtn.click(); return true; }
                }
            }
            return false;
        }
    """, post_num)

    page.wait_for_timeout(2500)
    if deleted:
        print(f"  ✅ 삭제 완료")
    else:
        print(f"  ⚠️  포스트를 찾지 못함 — 이미 삭제되었거나 페이지 확인 필요")


def set_content_and_publish(page, edit_url: str, html_content: str):
    """편집 URL로 이동해 본문을 교체하고 재발행"""
    page.goto(edit_url, wait_until="networkidle")
    page.wait_for_timeout(3000)

    # TinyMCE에 HTML 교체
    inserted = page.evaluate("""
        (html) => {
            if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
                tinymce.activeEditor.setContent(html);
                tinymce.activeEditor.fire('change');
                tinymce.activeEditor.save();
                return 'tinymce';
            }
            const iframe = document.querySelector('iframe.tox-edit-area__iframe');
            if (iframe) {
                const doc = iframe.contentDocument || iframe.contentWindow.document;
                const body = doc.querySelector('body');
                if (body) { body.innerHTML = html; return 'iframe'; }
            }
            return null;
        }
    """, html_content)
    page.wait_for_timeout(1500)
    print(f"  본문 교체: {inserted}")

    if not inserted:
        print("  ❌ 에디터 감지 실패 — 스킵")
        return

    # 완료 버튼 (발행 패널 오픈)
    try:
        page.get_by_role("button", name="완료").click(timeout=5000)
    except Exception:
        page.evaluate("""
            () => {
                const btn = [...document.querySelectorAll('button')]
                    .find(b => b.textContent.trim() === '완료');
                if (btn) btn.click();
            }
        """)
    page.wait_for_timeout(2500)

    # 공개 설정 (TreeWalker)
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
    try:
        page.get_by_role("button", name="공개 발행").click(timeout=5000)
        print("  ✅ '공개 발행' 클릭")
    except Exception:
        page.evaluate("""
            () => {
                const btn = [...document.querySelectorAll('button')]
                    .find(b => b.textContent.trim() === '공개 발행');
                if (btn) btn.click();
            }
        """)
        print("  ✅ '공개 발행' JS 클릭")

    # 발행 확인 (최대 10초)
    for _ in range(10):
        page.wait_for_timeout(1000)
        panel_gone = not page.locator("button:has-text('공개 발행')").is_visible()
        if panel_gone:
            break

    page.wait_for_timeout(2000)
    print(f"  ✅ 재발행 완료: {page.url}")


def edit_post(page, post_num: int, md_path: Path):
    """마크다운 파일을 HTML로 변환 후 기존 포스트 본문 교체"""
    print(f"\n[편집] 포스트 /{post_num} — {md_path.name}")

    # 편집 URL 탐색
    goto_manage_posts(page)
    edit_url = find_manage_url(page, post_num, "edit")
    if not edit_url:
        # 직접 시도 (내부 ID == 공개 번호인 경우)
        edit_url = f"https://{BLOG}.tistory.com/manage/post/{post_num}"
        print(f"  편집 URL 자동 탐지 실패 → 직접 시도: {edit_url}")
    else:
        print(f"  편집 URL: {edit_url}")

    # 마크다운 → HTML (hierarchical spacers 포함)
    _, html, _, _ = parse_blog_post(md_path)
    print(f"  HTML 길이: {len(html)}자")

    set_content_and_publish(page, edit_url, html)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
        page = context.new_page()

        login(page)

        # 1. 109, 110 삭제
        for num in DELETE_POST_NUMS:
            delete_post(page, num)

        # 2. 107, 108 편집
        for post_num, md_path in EDIT_POSTS:
            edit_post(page, post_num, md_path)

        browser.close()

    print("\n✅ 전체 완료")


if __name__ == "__main__":
    main()
