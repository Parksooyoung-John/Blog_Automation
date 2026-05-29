# Make.com 시나리오 가이드
## Notion → Tistory 자동 포스팅

---

## 전체 흐름

```
[Notion DB 감시]
  새 페이지 or 상태 변경 감지
        ↓
[Notion: 페이지 내용 읽기]
  제목, 본문, 태그, 카테고리
        ↓
[텍스트 가공] (선택사항)
  HTML 변환, 불필요 문자 제거
        ↓
[HTTP Module: Tistory API 호출]
  POST /post/write
        ↓
[Notion DB 상태 업데이트]
  "발행완료" 로 변경
```

---

## Notion DB 준비사항

스크립트 저장 DB에 아래 컬럼이 있어야 합니다:

| 컬럼명 | 타입 | 용도 |
|--------|------|------|
| 제목 | Title | 포스팅 제목 |
| 본문 | Text / Rich Text | 블로그 내용 |
| 태그 | Multi-select | 태그 목록 |
| 카테고리ID | Number | 티스토리 카테고리 번호 |
| 상태 | Select | `초안` / `발행대기` / `발행완료` |
| 발행일시 | Date | (선택) 예약 발행용 |

---

## Make.com 모듈 구성

### Module 1 — Notion: Watch Database Items
- **Database ID:** 노션 DB ID 입력
- **Filter 조건:** `상태` = `발행대기`
- **Polling interval:** 15분 또는 원하는 주기

### Module 2 — Notion: Get a Page
- **Page ID:** `{{1.id}}` (Module 1에서 받은 ID)
- 목적: 본문 전체 내용 가져오기

### Module 3 — Tools: Set variable (선택)
본문을 HTML로 가공이 필요할 경우:
- Notion의 rich text 블록을 HTML로 변환
- 줄바꿈 처리: `\n` → `<br>`

### Module 4 — HTTP: Make a Request
```
Method: POST
URL: https://www.tistory.com/apis/post/write

Query Parameters:
  access_token  : (환경변수 또는 직접 입력)
  blogName      : 내블로그
  title         : {{2.properties.제목.title[0].text.content}}
  content       : {{2.properties.본문.rich_text[0].text.content}}
  tag           : {{join(2.properties.태그.multi_select[*].name, ",")}}
  categoryId    : {{2.properties.카테고리ID.number}}
  visibility    : 3   ← 0:비공개, 1:보호, 3:공개
  published     : (선택) Unix timestamp
```

> ⚠️ Tistory API는 `content`에 **HTML** 형식을 사용합니다.

### Module 5 — Notion: Update a Database Item
- **Page ID:** `{{1.id}}`
- **상태** 컬럼 → `발행완료` 로 변경
- **발행일시** 컬럼 → `{{now}}` 로 기록

---

## 카테고리 ID 확인 방법

브라우저에서 아래 URL 접속 (토큰과 블로그명 교체):
```
https://www.tistory.com/apis/category/list?access_token=토큰&output=json&blogName=블로그명
```

응답 예시:
```json
{
  "item": {
    "categories": [
      {"id": "123456", "name": "역사심리학"},
      {"id": "123457", "name": "재테크"}
    ]
  }
}
```

---

## 에러 처리 권장사항

- Module 4 실패 시 → **Notion 상태를 `발행실패`로 업데이트**하는 Error Handler 추가
- Make.com 오른쪽 클릭 → `Add error handler` → `Rollback` 또는 `Resume`

---

## Python 후처리와 연동 포인트

Make.com이 포스팅 완료 후 Python 스크립트를 트리거하는 방법:

**옵션 A: Webhook 방식**
- Module 5 다음에 HTTP Module 추가
- 로컬 PC 또는 서버의 Python 스크립트 엔드포인트 호출
- 전달 데이터: `{ "post_id": "{{4.postId}}", "title": "{{2.properties.제목...}}" }`

**옵션 B: Notion 상태 폴링 방식**
- Python 스크립트가 주기적으로 실행 (Windows 작업 스케줄러)
- Notion DB에서 `발행완료` + `이미지처리대기` 상태인 항목 처리
- 처리 후 `전체완료`로 상태 변경
```
