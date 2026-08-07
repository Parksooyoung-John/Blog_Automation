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

from verify_post import print_verify_result

load_dotenv()
TISTORY_ID = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW = os.getenv("TISTORY_KAKAO_PASSWORD")
TISTORY_BLOG = os.getenv("TISTORY_BLOG_NAME")

WS = Path("_workspace")

# 업데이트할 포스트 번호 목록 (우선순위 순)
# 블록쿼트 삭제 버그 복구 — 신규 발행 /145, /146 (2026-07-17)
# 메타 필드 노출 버그 수정 — /145, /146 (2026-07-17)
# 애드센스 Phase 3 배치 A — 심화(3000자+/H2 5-7개) 반영
UPDATE_POSTS = [61, 95, 64, 85, 97]


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
    # ponytail: 로그인 직후 첫 네비게이션에서 networkidle이 30초 내 안 잡히는 경우가
    # 재현성 있게 발생함(에디터 페이지의 지속 연결 때문으로 추정, 2026-08-06 확인).
    # domcontentloaded로 완화 — 실제 로드 완료 여부는 아래 tinymce 대기가 보장한다.
    edit_url = f"https://{TISTORY_BLOG}.tistory.com/manage/post/{post_num}"
    try:
        page.goto(edit_url, wait_until="networkidle", timeout=30000)
    except Exception:
        print("  ⚠️  networkidle 대기 실패 — domcontentloaded로 재시도")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
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
                print_verify_result(f"/{post_num}", f"https://{TISTORY_BLOG}.tistory.com/{post_num}")
                # 처리 완료된 patch 파일은 즉시 삭제 — 다음 실행에서 잔존 파일이
                # 의도치 않게 재사용되는 사고를 막는다 (2026-07-16 발견된 이슈)
                (WS / f"enhanced_{post_num}.html").unlink(missing_ok=True)
            else:
                print(f"  ❌ /{post_num} 업데이트 실패 — 파일 보존 (재시도 가능)")
            page.wait_for_timeout(2000)

        browser.close()
    print("\n✅ 전체 처리 완료")


if __name__ == "__main__":
    main()
