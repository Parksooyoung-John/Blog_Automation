"""
Tistory 기존 포스트 내용 업데이트 — TinyMCE setContent로 교체
_workspace/enhanced_{num}.html 파일을 읽어 해당 포스트를 수정 발행한다.

Usage: python -X utf8 update_posts.py
"""
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page

load_dotenv()
TISTORY_ID = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW = os.getenv("TISTORY_KAKAO_PASSWORD")
TISTORY_BLOG = os.getenv("TISTORY_BLOG_NAME")

WS = Path("_workspace")

# 업데이트할 포스트 번호 목록 (우선순위 순)
UPDATE_POSTS = [122, 133, 131, 134, 106, 132, 127, 91]


def login(page: Page):
    page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
    page.click("a.btn_login.link_kakao_id")
    page.wait_for_load_state("networkidle")
    page.fill('input[name="loginId"]', TISTORY_ID)
    page.fill('input[name="password"]', TISTORY_PW)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    print(f"✅ 로그인 완료 (현재: {page.url})")


def update_post(page: Page, post_num: int) -> bool:
    enhanced_file = WS / f"enhanced_{post_num}.html"
    if not enhanced_file.exists():
        print(f"  ⚠️  {enhanced_file} 없음 — 건너뜀")
        return False

    new_html = enhanced_file.read_text(encoding="utf-8")
    print(f"  HTML 길이: {len(new_html)}자")

    # 편집 페이지 이동
    edit_url = f"https://{TISTORY_BLOG}.tistory.com/manage/post/{post_num}"
    page.goto(edit_url, wait_until="networkidle")
    page.wait_for_timeout(3000)
    print(f"  편집 페이지: {page.url}")

    # TinyMCE 로드 대기
    try:
        page.wait_for_function("() => typeof tinymce !== 'undefined' && tinymce.activeEditor !== null", timeout=15000)
    except Exception:
        print("  ⚠️  TinyMCE 로드 대기 중 재시도...")
        page.wait_for_timeout(3000)

    page.wait_for_timeout(1000)

    # 본문 설정
    page.evaluate("""
        (html) => {
            tinymce.activeEditor.setContent(html);
            tinymce.activeEditor.fire('change');
            tinymce.activeEditor.save();
        }
    """, new_html)
    print("  📝 본문 교체 완료")
    page.wait_for_timeout(1000)

    # "완료" 버튼 클릭 → 발행 패널
    clicked = page.evaluate("""
        () => {
            const btns = document.querySelectorAll('button, .btn');
            for (const btn of btns) {
                if (btn.textContent.trim() === '완료' && btn.offsetParent !== null) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }
    """)
    if not clicked:
        print("  ⚠️  '완료' 버튼 못 찾음")
        return False
    print("  🚀 '완료' 클릭 → 발행 패널 대기...")
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
    page.wait_for_timeout(500)

    # "공개 발행" or "수정하기" 버튼 클릭
    publish_clicked = page.evaluate("""
        () => {
            const keywords = ['공개 발행', '수정하기', '발행하기', '저장하기'];
            for (const kw of keywords) {
                const btns = document.querySelectorAll('button, [role="button"]');
                for (const btn of btns) {
                    if (btn.textContent.trim().includes(kw) && btn.offsetParent !== null && !btn.disabled) {
                        btn.click();
                        return kw;
                    }
                }
            }
            return null;
        }
    """)
    if publish_clicked:
        print(f"  ✅ '{publish_clicked}' 클릭")
    else:
        print("  ⚠️  발행 버튼 못 찾음")
        return False

    page.wait_for_timeout(3000)
    print(f"  현재 URL: {page.url}")
    return True


def main():
    available = [n for n in UPDATE_POSTS if (WS / f"enhanced_{n}.html").exists()]
    missing = [n for n in UPDATE_POSTS if n not in available]

    print(f"업데이트 예정: {available}")
    if missing:
        print(f"파일 없음 (건너뜀): {missing}")

    if not available:
        print("업데이트할 포스트 없음")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="ko-KR")
        page = context.new_page()

        login(page)

        for post_num in available:
            print(f"\n/{post_num} 업데이트 시작...")
            success = update_post(page, post_num)
            if success:
                print(f"  ✅ /{post_num} 업데이트 완료")
            else:
                print(f"  ❌ /{post_num} 업데이트 실패")
            page.wait_for_timeout(2000)

        browser.close()
    print("\n✅ 전체 처리 완료")


if __name__ == "__main__":
    main()
