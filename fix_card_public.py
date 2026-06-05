"""
신용카드 포스트를 공개로 변경하는 스크립트
실행: python -X utf8 fix_card_public.py
"""
from playwright.sync_api import sync_playwright
import os
from dotenv import load_dotenv
load_dotenv()

BLOG = os.getenv('TISTORY_BLOG_NAME')
ID   = os.getenv('TISTORY_KAKAO_EMAIL')
PW   = os.getenv('TISTORY_KAKAO_PASSWORD')

# 비공개 상태인 신용카드 포스트 ID
CARD_POST_IDS = [39, 41, 42, 49]

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, slow_mo=600)
    page = browser.new_context(viewport={'width': 1280, 'height': 900}, locale='ko-KR').new_page()

    # 로그인
    page.goto('https://www.tistory.com/auth/login', wait_until='networkidle')
    page.click('a.btn_login.link_kakao_id')
    page.wait_for_load_state('networkidle')
    page.fill('input[name="loginId"]', ID)
    page.fill('input[name="password"]', PW)
    page.click('button[type="submit"]')
    page.wait_for_load_state('networkidle')
    print('✅ 로그인 완료')

    for post_id in CARD_POST_IDS:
        print(f'\n포스트 /{post_id} 공개 전환 중...')
        page.goto(f'https://{BLOG}.tistory.com/manage/newpost/{post_id}', wait_until='networkidle')
        page.wait_for_timeout(3000)

        # 완료 버튼 → 발행 패널
        try:
            page.get_by_role('button', name='완료').click()
        except Exception:
            page.locator('button', has_text='완료').first.click()
        page.wait_for_timeout(2500)

        # 공개 라디오 클릭
        clicked = page.evaluate("""
            () => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while (node = walker.nextNode()) {
                    if (node.textContent.trim() === '공개') {
                        const el = node.parentElement;
                        if (el && el.offsetParent !== null) { el.click(); return el.tagName; }
                    }
                }
                return null;
            }
        """)
        print(f'  공개 설정: {clicked}')
        page.wait_for_timeout(1000)

        # 공개 발행
        try:
            page.get_by_role('button', name='공개 발행').click(timeout=5000)
            page.wait_for_timeout(4000)
            print(f'  ✅ /{post_id} 공개 발행 완료')
        except Exception as e:
            print(f'  ⚠️  /{post_id} 실패: {e}')

    browser.close()
    print('\n✅ 전체 완료')
