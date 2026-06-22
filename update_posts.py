"""
Tistory 포스트 일괄 수정 유틸
- 109, 110 삭제 (중복 주제)
- 107, 108 본문 계층 여백 재적용 (hierarchical spacers)

탐색 방법: 제목 텍스트로 포스트 행 찾기 (공개 URL이 manage 페이지에 링크되지 않음)
"""

import os, importlib.util
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BLOG = os.getenv("TISTORY_BLOG_NAME")
TISTORY_ID = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW = os.getenv("TISTORY_KAKAO_PASSWORD")

# parse_blog_post 임포트
_spec = importlib.util.spec_from_file_location(
    "notion_upload", Path(__file__).parent / "04_notion_upload.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
parse_blog_post = _mod.parse_blog_post

# 제목 키워드로 탐색 → (삭제용, 편집용)
DELETE_POSTS = [
    "청년미래적금",   # /109
    "국민성장 ISA",   # /110
]

EDIT_POSTS = [
    ("퇴직연금", Path(__file__).parent / "_workspace" / "blog_107_퇴직연금.md"),
    ("기초연금", Path(__file__).parent / "_workspace" / "blog_108_기초연금.md"),
]


def login(page):
    page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
    page.click("a.btn_login.link_kakao_id")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    page.fill('input[name="loginId"]', TISTORY_ID)
    page.fill('input[name="password"]', TISTORY_PW)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    if "tistory.com/manage" in page.url or "tistory.com" in page.url:
        print(f"✅ 로그인 완료: {page.url}")
    else:
        page.screenshot(path="debug_login_fail.png")
        raise Exception(f"로그인 실패: {page.url}")


def goto_manage_posts(page):
    page.goto(f"https://{BLOG}.tistory.com/manage/posts/", wait_until="networkidle")
    page.wait_for_timeout(3000)  # AJAX 로딩 대기
    # 디버그: 포스트가 로드됐는지 확인
    cnt = page.evaluate("() => document.querySelectorAll('a.btn_post').length")
    print(f"  manage/posts 버튼 수: {cnt}")
    if cnt == 0:
        page.screenshot(path="debug_manage_posts.png")
        print("  ⚠️  포스트 목록 로딩 실패 — debug_manage_posts.png 저장됨")


def find_row_by_title(page, keyword: str) -> dict | None:
    """제목에 keyword가 포함된 포스트 행의 편집 URL과 삭제 버튼 존재 여부 반환"""
    return page.evaluate("""
        (kw) => {
            const items = document.querySelectorAll('li');
            for (const item of items) {
                if (!item.textContent.includes(kw)) continue;
                const editLink = item.querySelector('a[href*="/manage/post/"]');
                const delBtn   = item.querySelector('a.btn_post[href="#"]');
                if (editLink || delBtn) {
                    return {
                        editHref: editLink ? editLink.href : null,
                        hasDelBtn: !!delBtn,
                        text: item.textContent.trim().slice(0, 60),
                    };
                }
            }
            return null;
        }
    """, keyword)


def delete_post(page, title_keyword: str):
    """제목에 keyword가 포함된 포스트 삭제"""
    print(f"\n[삭제] 키워드: '{title_keyword}'")
    goto_manage_posts(page)

    row = find_row_by_title(page, title_keyword)
    if not row:
        print(f"  ⚠️  포스트를 찾지 못함")
        return

    print(f"  발견: {row['text']}")
    if not row['hasDelBtn']:
        print(f"  ⚠️  삭제 버튼 없음")
        return

    # dialog 핸들러 등록 후 JS 클릭
    page.once("dialog", lambda d: d.accept())
    page.evaluate("""
        (kw) => {
            const items = document.querySelectorAll('li');
            for (const item of items) {
                if (!item.textContent.includes(kw)) continue;
                const delBtn = item.querySelector('a.btn_post[href="#"]');
                if (delBtn) { delBtn.click(); return true; }
            }
            return false;
        }
    """, title_keyword)
    page.wait_for_timeout(3000)
    print(f"  ✅ 삭제 완료")


def set_content_and_publish(page, edit_url: str, html_content: str):
    """편집 URL로 이동해 본문을 교체하고 재발행"""
    page.goto(edit_url, wait_until="networkidle")
    page.wait_for_timeout(3000)

    # TinyMCE 에디터 확인
    has_tinymce = page.evaluate("() => typeof tinymce !== 'undefined' && !!tinymce.activeEditor")
    if not has_tinymce:
        page.screenshot(path=f"debug_edit_{edit_url.split('/')[-1]}.png")
        print(f"  ❌ TinyMCE 없음 — {page.url}")
        return

    # 본문 교체
    page.evaluate("""
        (html) => {
            tinymce.activeEditor.setContent(html);
            tinymce.activeEditor.fire('change');
            tinymce.activeEditor.save();
        }
    """, html_content)
    page.wait_for_timeout(1500)
    print(f"  본문 교체 완료")

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
    page.wait_for_timeout(1000)

    # 공개 발행
    try:
        page.get_by_role("button", name="공개 발행").click(timeout=5000)
    except Exception:
        page.evaluate("""
            () => {
                const btn = [...document.querySelectorAll('button')]
                    .find(b => b.textContent.trim() === '공개 발행');
                if (btn) btn.click();
            }
        """)

    # 발행 확인
    for _ in range(10):
        page.wait_for_timeout(1000)
        if not page.locator("button:has-text('공개 발행')").is_visible():
            break

    page.wait_for_timeout(2000)
    print(f"  ✅ 재발행: {page.url}")


def edit_post(page, title_keyword: str, md_path: Path):
    print(f"\n[편집] 키워드: '{title_keyword}' — {md_path.name}")
    goto_manage_posts(page)

    row = find_row_by_title(page, title_keyword)
    if not row or not row.get("editHref"):
        print(f"  ❌ 편집 URL 못 찾음 — 스킵")
        return

    edit_url = row["editHref"]
    print(f"  편집 URL: {edit_url}")
    print(f"  발견: {row['text']}")

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

        # 1. 삭제
        for keyword in DELETE_POSTS:
            delete_post(page, keyword)

        # 2. 편집
        for keyword, md_path in EDIT_POSTS:
            edit_post(page, keyword, md_path)

        browser.close()

    print("\n✅ 전체 완료")


if __name__ == "__main__":
    main()
