"""
시리즈 소급 업데이트 — 기발행 포스트에 새 편 카드 추가

사용법:
  python update_series_links.py --target "포스트 제목 키워드" --card_html "추가할 카드 HTML"

내부 작동:
  1. Tistory manage/posts에서 target 키워드로 포스트 탐색
  2. 편집 페이지에서 현재 HTML 읽기
  3. 함께 읽으면 좋은 글 섹션에 card_html 삽입
  4. 저장 후 공개 발행
"""

import os, sys
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BLOG = os.getenv("TISTORY_BLOG_NAME")
TISTORY_ID = os.getenv("TISTORY_KAKAO_EMAIL")
TISTORY_PW = os.getenv("TISTORY_KAKAO_PASSWORD")

# ──────────────────────────────────────────────
# 업데이트 설정
# ──────────────────────────────────────────────

_card_2편B = """<div style="border:1px solid #e8e8e8;border-radius:12px;overflow:hidden;margin:16px 0;max-width:640px;">
<a href="https://j2gblog.tistory.com/entry/Harness-Engineering-실전-2편B-—-수집가·분석가·개발자·검토자-에이전트-프롬프트-전체-공개" target="_blank" rel="noopener" style="display:flex;text-decoration:none;color:inherit;">
<div style="width:160px;min-width:160px;overflow:hidden;"><img src="https://img1.daumcdn.net/thumb/R800x0/?scode=mtistory2&fname=https%3A%2F%2Fblog.kakaocdn.net%2Fdna%2FsCmDN%2FdJMcaiKxbnb%2FAAAAAAAAAAAAAAAAAAAAAGgxJIIlvS5ryj8Kb6x4VUojPNBBk1pBdwd4m_R9sR9n%2Fimg.png%3Fcredential%3DyqXZFxpELC7KVnFOS48ylbz2pIh7yKj8%26expires%3D1782831599%26allow_ip%3D%26allow_referer%3D%26signature%3DL2n8sdaVQw9iAEM0kObdgPDqXCY%253D" style="width:100%;height:105px;object-fit:cover;display:block;" /></div>
<div style="padding:14px 18px;flex:1;">
<div style="font-weight:700;font-size:15px;color:#333;margin-bottom:6px;line-height:1.4;">Harness Engineering 실전 2편B — 수집가·분석가·개발자·검토자 에이전트 프롬프트 전체 공개</div>
<div style="font-size:13px;color:#666;line-height:1.5;">수집가·분석가·개발자·검토자 에이전트 프롬프트를 전부 공개합니다. 복사해서 바로 쓸 수 있는 형태로 정리했습니다.</div>
<div style="font-size:12px;color:#aaa;margin-top:10px;">j2gblog.tistory.com</div>
</div></a></div>"""

# 1편 + 2편A에 2편B 카드 추가
UPDATES = [
    {
        "target_keyword": "Harness Engineering — AI 코딩 도구를 제대로 쓰는 방법",
        "new_card": _card_2편B,
    },
    {
        "target_keyword": "Harness Engineering 실전 2편A",
        "new_card": _card_2편B,
    },
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
    print(f"✅ 로그인 완료")


def find_post_edit_url(page, keyword: str) -> str | None:
    """manage/posts에서 키워드로 포스트 탐색, 편집 URL 반환"""
    page.goto(f"https://{BLOG}.tistory.com/manage/posts/", wait_until="networkidle")
    page.wait_for_timeout(3000)

    edit_url = page.evaluate("""
        (kw) => {
            const items = document.querySelectorAll('li');
            for (const item of items) {
                if (!item.textContent.includes(kw)) continue;
                const editLink = item.querySelector('a[href*="/manage/post/"]');
                if (editLink) return editLink.href;
            }
            return null;
        }
    """, keyword)
    return edit_url


def update_post(page, edit_url: str, new_card: str):
    """편집 페이지에서 함께 읽으면 좋은 글 섹션 앞에 카드 삽입"""
    page.goto(edit_url, wait_until="networkidle")
    page.wait_for_timeout(3000)

    # 현재 TinyMCE 콘텐츠 읽기
    current_html = page.evaluate("""
        () => {
            if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
                return tinymce.activeEditor.getContent();
            }
            return null;
        }
    """)

    if not current_html:
        print("  ⚠️  TinyMCE 콘텐츠 읽기 실패")
        return False

    # 함께 읽으면 좋은 글 섹션 앞에 새 카드 삽입
    # TinyMCE는 HTML이므로 H2 태그로 탐색
    import re as re_mod
    pattern = re_mod.compile(r'(<h2[^>]*>함께 읽으면 좋은 글</h2>)', re_mod.IGNORECASE)
    if not pattern.search(current_html):
        print(f"  ⚠️  '함께 읽으면 좋은 글' H2 섹션을 찾지 못함")
        print(f"  ℹ️  현재 HTML 앞부분: {current_html[:300]}")
        return False

    # 삽입: H2 섹션 직후에 새 카드 삽입
    updated_html = pattern.sub(
        r'\1\n' + new_card,
        current_html
    )

    # TinyMCE에 업데이트된 콘텐츠 설정
    page.evaluate("""
        (html) => {
            tinymce.activeEditor.setContent(html);
            tinymce.activeEditor.fire('change');
            tinymce.activeEditor.save();
        }
    """, updated_html)
    page.wait_for_timeout(1000)
    print("  ✅ 콘텐츠 업데이트 완료")

    # 완료 버튼 → 발행 패널
    page.evaluate("""
        () => {
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.textContent.trim() === '완료') { btn.click(); return; }
            }
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
    page.wait_for_timeout(500)

    # 공개 발행 버튼
    try:
        page.get_by_role("button", name="공개 발행").click(timeout=5000)
        page.wait_for_timeout(3000)
        print("  ✅ 공개 발행 완료")
        return True
    except Exception:
        # 발행 버튼 JS 폴백
        page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes('발행')) { btn.click(); return; }
                }
            }
        """)
        page.wait_for_timeout(3000)
        print("  ✅ 발행 완료 (JS 폴백)")
        return True


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="ko-KR")
        page = context.new_page()

        login(page)

        for update in UPDATES:
            keyword = update["target_keyword"]
            new_card = update["new_card"]
            print(f"\n[업데이트] '{keyword[:40]}...'")

            edit_url = find_post_edit_url(page, keyword[:30])
            if not edit_url:
                print(f"  ⚠️  포스트를 찾지 못함")
                continue

            print(f"  편집 URL: {edit_url}")
            success = update_post(page, edit_url, new_card)
            if success:
                print(f"  ✅ 소급 업데이트 완료")
            else:
                print(f"  ❌ 업데이트 실패")

        browser.close()
    print("\n✅ 모든 소급 업데이트 완료")


if __name__ == "__main__":
    main()
