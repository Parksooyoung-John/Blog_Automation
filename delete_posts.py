"""
Tistory 특정 포스트 삭제 — manage/posts 페이지에서 제목 텍스트로 매칭
Usage: python -X utf8 delete_posts.py
"""
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
TISTORY_ID = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW = os.getenv("TISTORY_KAKAO_PASSWORD")
TISTORY_BLOG = os.getenv("TISTORY_BLOG_NAME")

# 삭제할 포스트 번호 (public URL number)
DELETE_POST_NUMS = [129, 130]


def login(page):
    page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
    page.click("a.btn_login.link_kakao_id")
    page.wait_for_load_state("networkidle")
    page.fill('input[name="loginId"]', TISTORY_ID)
    page.fill('input[name="password"]', TISTORY_PW)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    print(f"  현재 URL: {page.url}")
    print("✅ 로그인 완료")


def get_posts_on_page(page):
    """현재 manage/posts 페이지에서 (제목, 수정링크href) 목록 반환"""
    return page.evaluate("""
        () => {
            const result = [];
            const rows = document.querySelectorAll('li');
            rows.forEach(row => {
                const editLink = row.querySelector('a.btn_post[href*="/manage/post/"]');
                const titleEl = row.querySelector('a.link_post') || row.querySelector('.post_item strong') || row.querySelector('strong.tit_post');
                if (editLink && titleEl) {
                    result.push({
                        href: editLink.href,
                        title: titleEl.textContent.trim()
                    });
                }
            });
            return result;
        }
    """)


def delete_by_edit_href(page, edit_href):
    """수정 링크 href를 기준으로 같은 행의 삭제 버튼을 클릭"""
    # dialog 핸들러 먼저 등록
    page.on("dialog", lambda d: d.accept())

    deleted = page.evaluate("""
        (href) => {
            const editLinks = document.querySelectorAll('a.btn_post[href*="/manage/post/"]');
            for (const link of editLinks) {
                if (link.href === href || link.href.includes(href)) {
                    const row = link.closest('li');
                    if (!row) continue;
                    const delBtn = row.querySelector('a.btn_post[href="#"]');
                    if (delBtn) {
                        delBtn.click();
                        return true;
                    }
                }
            }
            return false;
        }
    """, edit_href)
    return deleted


def delete_post(page, post_num):
    """manage/posts를 여러 페이지 순회하여 post_num에 해당하는 포스트 삭제"""
    base_url = f"https://{TISTORY_BLOG}.tistory.com/manage/posts"
    page_num = 1

    while True:
        url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1000)

        posts = get_posts_on_page(page)
        if not posts:
            print(f"  /{post_num}: 더 이상 페이지 없음 — 찾지 못함")
            return False

        print(f"  페이지 {page_num}: {len(posts)}개 포스트 확인")

        # /manage/post/{post_num}? 가 포함된 href 찾기
        target_href = None
        for p in posts:
            if f"/manage/post/{post_num}" in p["href"] or f"/manage/post/{post_num}?" in p["href"]:
                target_href = p["href"]
                print(f"  /{post_num} 발견: {p['title'][:50]}")
                break

        if target_href:
            # dialog 핸들러 등록 후 삭제
            dialog_accepted = [False]

            def handle_dialog(d):
                print(f"  dialog: {d.message[:50]}")
                d.accept()
                dialog_accepted[0] = True

            page.on("dialog", handle_dialog)

            result = page.evaluate("""
                (href) => {
                    const editLinks = document.querySelectorAll('a.btn_post[href*="/manage/post/"]');
                    for (const link of editLinks) {
                        if (link.href.includes(href)) {
                            const row = link.closest('li');
                            if (!row) return 'no-row';
                            const delBtn = row.querySelector('a.btn_post[href="#"]');
                            if (delBtn) { delBtn.click(); return 'clicked'; }
                            return 'no-del-btn';
                        }
                    }
                    return 'not-found';
                }
            """, f"/manage/post/{post_num}")

            page.wait_for_timeout(2000)
            print(f"  JS 결과: {result}, dialog 처리: {dialog_accepted[0]}")

            if result == "clicked":
                return True
            else:
                print(f"  /{post_num}: 삭제 버튼 클릭 실패 ({result})")
                return False

        # 다음 페이지 확인
        has_next = page.evaluate("""
            () => {
                const nextLinks = document.querySelectorAll('a[href*="page="]');
                return nextLinks.length > 0;
            }
        """)

        if not has_next or page_num >= 10:
            print(f"  /{post_num}: 10페이지까지 찾지 못함")
            return False

        page_num += 1


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="ko-KR"
        )
        page = context.new_page()

        login(page)

        for post_num in DELETE_POST_NUMS:
            print(f"\n/{post_num} 삭제 시도...")
            # manage/posts 페이지 진입 전 현재 URL 확인
            print(f"  이동 전 URL: {page.url}")
            success = delete_post(page, post_num)
            if success:
                print(f"  ✅ /{post_num} 삭제 완료")
            else:
                print(f"  ❌ /{post_num} 삭제 실패")

        page.wait_for_timeout(2000)
        browser.close()
        print("\n완료")


if __name__ == "__main__":
    main()
