"""티스토리에 사람이 직접 한 번 로그인해 세션을 저장한다.

카카오가 자동 로그인에 캡차를 띄우기 시작해(2026-09) 스크립트가 아이디·비밀번호를
입력하는 방식은 더 이상 안정적으로 동작하지 않는다. 사람이 브라우저에서 직접 로그인하고
그 쿠키를 저장해두면, 이후 발행 스크립트는 로그인 과정 없이 그 세션을 재사용한다.

사용법:
    python -X utf8 tistory_login_once.py
브라우저가 열리면 카카오 로그인을 직접 완료한다(캡차가 나오면 사람이 푼다).
로그인이 확인되면 .auth/tistory_state.json 에 세션을 저장하고 자동으로 닫힌다.

주의: 사용자가 입력 중인 탭은 절대 건드리지 않는다. 대기 중 그 탭을 goto로 이동시키면
입력하던 화면이 새로고침돼 로그인을 방해한다(2026-09-19 실제로 발생). 감지는 쿠키와
URL 읽기로만 하고, 확인이 필요하면 별도 탭을 열어서 한다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(Path(__file__).parent / ".env")
BLOG = os.getenv("TISTORY_BLOG_NAME", "j2gblog")
AUTH_PATH = Path(__file__).parent / ".auth" / "tistory_state.json"
WAIT_MINUTES = 15


def _logged_in_cookie(ctx) -> bool:
    for c in ctx.cookies():
        if "tistory.com" in c.get("domain", "") and c.get("name") in (
            "TSSESSION", "TISTORY_SESSION", "_T_SESSION", "TSSESSION_SECURE"
        ):
            return True
    return False


def main():
    AUTH_PATH.parent.mkdir(exist_ok=True)
    profile_dir = AUTH_PATH.parent / "chrome_profile"
    with sync_playwright() as pw:
        # Playwright 기본 Chromium은 자동화 표식이 노출돼 카카오가 입력 도중 화면을 새로
        # 고침해버린다(2026-09-19 확인). 실제 크롬 채널 + AutomationControlled 해제로 띄운다.
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tistory.com/auth/login", wait_until="domcontentloaded")

        print("=" * 64)
        print(" 브라우저에서 카카오 로그인을 직접 완료하세요.")
        print(" 캡차(보안 문제)가 나오면 직접 푸시면 됩니다.")
        print(" 이 창은 입력을 방해하지 않도록 아무것도 건드리지 않고 기다립니다.")
        print(f" 로그인이 확인되면 저장 후 자동으로 닫힙니다. (최대 {WAIT_MINUTES}분)")
        print("=" * 64)

        waited, deadline = 0, WAIT_MINUTES * 60
        while waited < deadline:
            page.wait_for_timeout(3000)
            waited += 3
            try:
                url = page.url  # 읽기만 한다
            except Exception:
                break
            back_on_tistory = "tistory.com" in url and "auth/login" not in url
            if back_on_tistory or _logged_in_cookie(ctx):
                page.wait_for_timeout(3000)
                probe = ctx.new_page()  # 사용자 탭 대신 새 탭에서 확인
                try:
                    probe.goto(f"https://{BLOG}.tistory.com/manage/newpost",
                               wait_until="domcontentloaded")
                    probe.wait_for_timeout(3000)
                    ok = probe.locator('textarea#title, input#title, [placeholder*="제목"]').count() > 0
                finally:
                    probe.close()
                if ok:
                    ctx.storage_state(path=str(AUTH_PATH))
                    print(f"\n로그인 확인. 세션 저장: {AUTH_PATH}")
                    print("이제 발행 스크립트가 이 세션을 재사용합니다.")
                    ctx.close()
                    return
            if waited % 30 == 0:
                print(f"  대기 중... {waited}초 (현재: {url[:60]})")

        print("시간 초과. 로그인이 확인되지 않아 저장하지 않았습니다.")
        ctx.close()


if __name__ == "__main__":
    main()
