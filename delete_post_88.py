"""
Tistory 포스트 삭제 스크립트 — /88 정정용
"""

import os
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BLOG = os.getenv("TISTORY_BLOG_NAME")
EMAIL = os.getenv("TISTORY_KAKAO_EMAIL")
PW = os.getenv("TISTORY_KAKAO_PASSWORD")
POST_ID = "88"

def delete_post():
    print(f"🗑️  Tistory 포스트 /{POST_ID} 삭제 시작...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ko-KR"
        )
        page = context.new_page()

        # 로그인
        print("🔐 로그인 중...")
        page.goto(f"https://{BLOG}.tistory.com/manage/posts", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # 카카오 로그인 버튼 클릭
        try:
            page.click('a.btn_login.link_kakao_id')
            page.wait_for_load_state("networkidle")

            # 카카오 이메일/비밀번호 입력
            page.fill('input[name="loginId"]', EMAIL)
            page.fill('input[name="password"]', PW)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            print("✅ 로그인 완료")
        except Exception as e:
            print(f"⚠️  이미 로그인 상태이거나 로그인 버튼 없음: {e}")

        # 관리 페이지로 이동 (로그인 직후 리다이렉트 대응)
        page.goto(f"https://{BLOG}.tistory.com/manage/posts", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # dialog 핸들러 먼저 등록 (삭제 확인 대화상자)
        page.on("dialog", lambda d: d.accept())

        # 해당 포스트 삭제 버튼 JS 클릭
        print(f"🔍 포스트 /{POST_ID} 찾는 중...")
        result = page.evaluate(f"""
            () => {{
                const editLinks = document.querySelectorAll('a.btn_post[href*="/manage/post/{POST_ID}"]');
                if (!editLinks.length) return false;
                const row = editLinks[0].closest('li');
                const delBtn = row.querySelector('a.btn_post[href="#"]');
                if (delBtn) {{
                    delBtn.click();
                    return true;
                }}
                return false;
            }}
        """)

        page.wait_for_timeout(2500)
        browser.close()

        if result:
            print("✅ 삭제 버튼 클릭 완료")
            # 삭제 확인
            print("🔍 삭제 확인 중...")
            try:
                r = requests.get(f"https://{BLOG}.tistory.com/{POST_ID}", timeout=10)
                if r.status_code == 404:
                    print(f"✅ 포스트 /{POST_ID} 삭제 완료 (404 확인)")
                else:
                    print(f"⚠️  포스트 여전히 존재 (HTTP {r.status_code})")
            except Exception as e:
                print(f"⚠️  삭제 확인 실패: {e}")
        else:
            print(f"❌ 포스트 /{POST_ID} 찾을 수 없음 (이미 삭제됨 또는 번호 오류)")

if __name__ == "__main__":
    delete_post()
