"""Tistory 포스트 /111, /112 삭제"""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BLOG = os.getenv("TISTORY_BLOG_NAME")
TISTORY_ID = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW = os.getenv("TISTORY_KAKAO_PASSWORD")

DELETE_KEYWORDS = [
    "착한가격업소",   # /111
    "미성년자 카드",  # /112
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
    if "tistory.com" in page.url:
        print(f"✅ 로그인 완료: {page.url}")
    else:
        raise Exception(f"로그인 실패: {page.url}")


def delete_post(page, keyword: str):
    print(f"\n[삭제] 키워드: '{keyword}'")
    page.goto(f"https://{BLOG}.tistory.com/manage/posts/", wait_until="networkidle")
    page.wait_for_timeout(3000)

    row = page.evaluate("""
        (kw) => {
            const items = document.querySelectorAll('li');
            for (const item of items) {
                if (!item.textContent.includes(kw)) continue;
                const editLink = item.querySelector('a[href*="/manage/post/"]');
                const delBtn   = item.querySelector('a.btn_post[href="#"]');
                if (editLink || delBtn) {
                    return {
                        hasDelBtn: !!delBtn,
                        text: item.textContent.trim().slice(0, 80),
                    };
                }
            }
            return null;
        }
    """, keyword)

    if not row:
        print(f"  ⚠️  포스트를 찾지 못함 — 이미 삭제됐거나 제목 불일치")
        return

    print(f"  발견: {row['text']}")
    if not row['hasDelBtn']:
        print(f"  ⚠️  삭제 버튼 없음")
        return

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
    """, keyword)
    page.wait_for_timeout(3000)
    print(f"  ✅ 삭제 완료")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="ko-KR")
        page = context.new_page()

        login(page)

        for keyword in DELETE_KEYWORDS:
            delete_post(page, keyword)

        browser.close()
    print("\n✅ 삭제 완료")


if __name__ == "__main__":
    main()
