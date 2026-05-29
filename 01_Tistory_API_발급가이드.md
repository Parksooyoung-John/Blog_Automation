# 티스토리 API 발급 가이드

## Step 1. 티스토리 오픈 API 앱 등록

1. **티스토리 로그인** 후 아래 주소 접속
   ```
   https://www.tistory.com/guide/api/manage/register
   ```

2. **앱 등록 정보 입력:**
   | 항목 | 입력값 예시 |
   |------|------------|
   | 서비스명 | 내 블로그 자동화 |
   | 설명 | 자동 포스팅 시스템 |
   | 서비스 URL | https://내블로그.tistory.com |
   | CallBack URL | https://localhost (로컬 테스트용) |

3. 등록 완료 후 **App ID (Client ID)** 와 **Secret Key** 저장

---

## Step 2. Access Token 발급 (브라우저에서 직접)

### 2-1. 인증 코드 받기
아래 URL을 브라우저 주소창에 입력 (APP_ID 부분을 실제 값으로 교체):

```
https://www.tistory.com/oauth/authorize?client_id=APP_ID&redirect_uri=https://localhost&response_type=code
```

→ 인증 완료 후 브라우저 주소창에 표시되는 URL에서 `code=` 뒤의 값 복사

예시:
```
https://localhost/?code=여기가_인증코드
```

### 2-2. Access Token 발급
아래 URL을 브라우저에서 접속 (각 값 교체):

```
https://www.tistory.com/oauth/access_token?client_id=APP_ID&client_secret=SECRET_KEY&redirect_uri=https://localhost&code=인증코드&grant_type=authorization_code
```

→ 응답으로 받은 `access_token=` 뒤의 값이 **최종 Access Token**

---

## Step 3. 환경변수 파일(.env) 저장

프로젝트 폴더에 `.env` 파일 생성 후 저장:

```env
TISTORY_ACCESS_TOKEN=여기에_토큰_입력
TISTORY_BLOG_NAME=내블로그  # 블로그 주소의 서브도메인 (내블로그.tistory.com)

NOTION_API_KEY=여기에_노션_API_키
NOTION_DATABASE_ID=여기에_노션_DB_ID

OPENAI_API_KEY=여기에_OpenAI_키  # 썸네일 이미지 생성용
COUPANG_PARTNER_ID=여기에_쿠팡_파트너_ID  # 선택사항
```

> ⚠️ `.env` 파일은 절대 깃허브에 올리지 말 것!

---

## Step 4. Notion API 키 발급

1. https://www.notion.so/my-integrations 접속
2. **New integration** 클릭
3. 이름 입력 후 생성 → **Internal Integration Token** 복사
4. Notion에서 스크립트가 저장된 **데이터베이스 페이지** 열기
   → 우측 상단 `...` → `Connections` → 방금 만든 integration 추가

---

## 확인 사항 체크리스트

- [ ] Tistory App ID 발급 완료
- [ ] Tistory Secret Key 발급 완료  
- [ ] Tistory Access Token 발급 완료
- [ ] Notion Integration Token 발급 완료
- [ ] Notion Database ID 확인 완료 (DB URL의 마지막 32자리)
- [ ] `.env` 파일 생성 완료
