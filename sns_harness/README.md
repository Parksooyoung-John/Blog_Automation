# Tistory → Threads SNS Harness

`j2gblog.tistory.com`의 게시물을 읽어 Threads 계정 `money.ybrief`용 초안을 만들고,
별도 Notion 승인 큐에서 승인된 글만 예약 시각에 공식 Threads API로 게시하는 Python 패키지입니다.

## 안전 경계

- LLM은 초안 생성과 검수만 수행하며 Notion이나 Threads에 직접 쓰지 않습니다.
- `초안`을 사용자가 `승인`으로 변경하기 전에는 게시되지 않습니다.
- 게시 완료 글의 원문이 바뀌어도 재게시하지 않습니다.
- 기존 `블로그자동화` 발행 DB와 코드를 사용하거나 수정하지 않습니다.

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

```powershell
# 첫 도입 시 최신 10건을 승인 큐에 생성
.\.venv\Scripts\python.exe -m sns_harness sync --backfill 10

# 이후 최근 48시간에 발행된 신규 글만 동기화
.\.venv\Scripts\python.exe -m sns_harness sync

# 승인된 항목의 빈 예약시각을 배정하고, 도래한 항목 최대 1건 게시
.\.venv\Scripts\python.exe -m sns_harness publish-due

# 외부 상태를 바꾸지 않는 후보/게시 대상 확인
.\.venv\Scripts\python.exe -m sns_harness sync --dry-run
.\.venv\Scripts\python.exe -m sns_harness publish-due --dry-run
```

운영 준비와 장애 복구는 [RUNBOOK](docs/RUNBOOK.md)을 따릅니다.
