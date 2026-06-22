"""manage/posts DOM 구조 확인 — 링크 목록 덤프"""
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BLOG = os.getenv("TISTORY_BLOG_NAME")
TISTORY_ID = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW = os.getenv("TISTORY_KAKAO_PASSWORD")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=300)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="ko-KR")

        page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
        page.click("a.btn_login.link_kakao_id")
        page.wait_for_load_state("networkidle")
        page.fill('input[name="loginId"]', TISTORY_ID)
        page.fill('input[name="password"]', TISTORY_PW)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        print("로그인 완료")

        page.goto(f"https://{BLOG}.tistory.com/manage/posts/", wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path="debug_manage_posts.png")

        # 모든 링크 덤프
        links = page.evaluate("""
            () => {
                return [...document.querySelectorAll('a')].map(a => ({
                    text: a.textContent.trim().slice(0, 40),
                    href: a.href.slice(0, 100)
                })).filter(l => l.href);
            }
        """)
        print(f"\n총 {len(links)}개 링크:")
        for l in links:
            print(f"  [{l['text']}] {l['href']}")

        # li 구조 덤프 (첫 5개)
        items = page.evaluate("""
            () => {
                const rows = document.querySelectorAll('li');
                return [...rows].slice(0, 10).map(li => ({
                    text: li.textContent.trim().slice(0, 80),
                    html: li.innerHTML.slice(0, 300)
                }));
            }
        """)
        print(f"\nli 요소 샘플:")
        for item in items:
            print(f"  TEXT: {item['text'][:60]}")
            print(f"  HTML: {item['html'][:200]}")
            print()

        browser.close()


if __name__ == "__main__":
    main()
