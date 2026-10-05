# Naver → Threads SNS Harness

네이버 블로그 `education_blog`의 공개 게시물을 읽어 Threads 계정 `mone.ybrief`용 초안을 만들고,
별도 Notion 승인 큐에서 승인된 글만 예약 시각에 공식 Threads API로 게시하는 Python 패키지입니다.

## 안전 경계

- LLM은 초안 생성과 검수만 수행하며 Notion이나 Threads에 직접 쓰지 않습니다.
- `초안`을 사용자가 `승인`으로 변경하기 전에는 게시되지 않습니다.
- 게시 완료 글의 원문이 바뀌어도 재게시하지 않습니다.
- 기존 티스토리 게시 기록과 `TistorySource`는 호환성을 위해 보존하지만 자동 수집·예약·게시
  대상에서는 제외합니다.
- 네이버는 공개 글을 읽기만 하며 네이버 작성·수정·삭제 기능은 제공하지 않습니다.
- 상품 제휴 답글은 Notion에서 명시적으로 요청하고 다시 승인한 항목에만 추가됩니다.

## 설치

```powershell
cd 블로그자동화\sns_harness
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

`.env`를 채우고 [Notion 스키마](docs/NOTION_SCHEMA.md)를 만든 뒤 검증합니다.

```powershell
.\.venv\Scripts\python.exe -m sns_harness validate-config
```

## 운영 명령

기본 예약 슬롯은 KST 08:30(재테크팁), 12:30(블로그정보), 16:30(질문형),
21:30(운영글)입니다. 운영글은 운영메모와 사람 수정이 없으면 승인할 수 없습니다.

```powershell
# 네이버 최신 10건을 승인 큐에 생성
.\.venv\Scripts\python.exe -m sns_harness sync --backfill 10

# 네이버 신규 글 동기화(--source naver가 기본값)
.\.venv\Scripts\python.exe -m sns_harness sync

# 오류 항목을 최신 원문으로 재생성하고 초안으로 되돌림
.\.venv\Scripts\python.exe -m sns_harness sync --retry-errors

# 미게시 네이버 블로그 글을 Hook 강화 기준으로 미리 검토/재생성
.\.venv\Scripts\python.exe -m sns_harness regenerate-blog-hooks --dry-run
.\.venv\Scripts\python.exe -m sns_harness regenerate-blog-hooks

# 승인된 항목의 빈 예약시각을 배정하고, 도래한 항목 최대 1건 게시
.\.venv\Scripts\python.exe -m sns_harness publish-due

# Notion에서 판매초안요청으로 바꾼 항목의 상품형 초안 생성
.\.venv\Scripts\python.exe -m sns_harness prepare-sales

# 외부 상태를 바꾸지 않는 후보/게시 대상 확인
.\.venv\Scripts\python.exe -m sns_harness sync --dry-run
.\.venv\Scripts\python.exe -m sns_harness publish-due --dry-run
.\.venv\Scripts\python.exe -m sns_harness prepare-sales --dry-run
```

## 상품 제휴 답글

상품 답글을 붙일 항목에 `판매플랫폼`, `상품명`, `상품URL`, `추천근거`를 입력하고 상태를
`판매초안요청`으로 변경합니다. 시간별 동기화 또는 수동 `prepare-sales`가 정보 글 1~4개와
마지막 판매 답글을 생성하고, 기존 예약을 지운 뒤 상태를 `초안`으로 되돌립니다. 전체 문구와
광고 고지를 확인한 후 다시 `승인`해야 예약됩니다.

v1은 `https://sharelink.toss.im/...`과 `https://link.coupang.com/...` 링크만 허용합니다.
상품 페이지의 가격·할인·재고는 자동 수집하지 않습니다. 고지문을 직접 바꾸려면 `[광고]`로
시작하고 수수료 지급 사실을 명확하게 적어야 합니다.

GitHub Actions 정기·수동 동기화는 네이버만 수집한 뒤 판매초안 요청도 처리합니다. 초안에는 해당 네이버 원문의 canonical
URL이 포함되며, 사람이 상태를 `승인`으로 바꾼 네이버 항목만 예약·게시됩니다. 기존
`--source tistory` CLI 선택지는 과거 데이터 점검 호환용으로만 남아 있습니다.

운영 준비와 장애 복구는 [RUNBOOK](docs/RUNBOOK.md)을 따릅니다.

## 운영자용 빠른 사용법

1. GitHub Actions가 네이버 글을 읽고 Notion에 `초안`을 만듭니다.
2. 모바일 Notion에서 `첫게시물`과 `답글1~4`를 확인합니다.
3. 내용이 맞으면 `상태`를 `승인`으로 바꿉니다.
4. 게시 workflow가 콘텐츠 유형에 맞는 가장 빠른 빈 슬롯을 예약합니다.
5. 게시 성공 시 `게시완료`, `ThreadsIDs`, `게시시각`이 기록됩니다.

`초안`이나 `보류` 상태는 자동 게시되지 않습니다. 승인했는데 예약시각이 비어 있으면
`publish-due`를 다시 실행하거나 GitHub Actions 게시 작업을 수동 실행하세요.

### 기획·성과 확인

네이버 데이터랩은 현재 자동화에 사용하지 않습니다. 신규 API 키 발급 제약 때문에
운영 판단은 Threads 공식 인사이트, 네이버 글의 공식 근거, 최근 게시 성과를 기준으로 합니다.

Notion의 `기획키워드`, `검색의도`, `트렌드지수`, `트렌드방향`, `콘텐츠목표`,
`Threads조회수`, `24시간조회수`, `72시간조회수`, `7일조회수`, `성과판정` 필드를
기획과 성과 기록에 사용합니다. API가 제공하지 않는 값은 `0`이 아니라 `미측정`으로 둡니다.
`블로그조회수`는 수동 입력이며 자동 성과 수집으로 덮어쓰지 않습니다.

자세한 절차는 [운영자 매뉴얼](docs/USER_MANUAL.md)을 참고하세요.

## Daily Operations Manager

매일 07:45 KST에 예약·오류·성과·데이터 누락을 분석해 별도 Notion 데이터베이스에
객관적인 운영 브리핑을 만듭니다. Manager는 게시 큐를 변경하지 않고 필요한 조치만 제안합니다.

```powershell
# 별도 Notion DB 속성 추가
.\.venv\Scripts\python.exe -m sns_harness operations setup-schema

# 외부 변경 없이 현재 판정과 필요한 데이터 확인
.\.venv\Scripts\python.exe -m sns_harness operations evaluate --days 30
.\.venv\Scripts\python.exe -m sns_harness operations data-gaps --days 30

# 오늘 브리핑 생성 또는 갱신
.\.venv\Scripts\python.exe -m sns_harness operations brief --date today --days 30
```

`NOTION_OPERATIONS_DATABASE_ID`에는 Title 속성명이 `이름`인 별도 데이터베이스 ID를 넣습니다.
4주·측정 가능 게시물 20건·3개 실험을 충족하기 전에는 콘셉트 실패를 단정하지 않습니다.
