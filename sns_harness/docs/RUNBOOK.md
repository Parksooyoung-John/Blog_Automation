# 운영 Runbook

## 최초 설정

1. Meta 개발자 앱에 Threads 사용 사례를 추가하고 `threads_basic`,
   `threads_content_publish` 권한의 장기 사용자 토큰과 Threads 사용자 ID를 준비한다.
2. 별도 Notion SNS DB를 `NOTION_SCHEMA.md`대로 생성하고 통합에 권한을 준다.
3. GitHub Secrets에 `OPENAI_API_KEY`, `NOTION_API_KEY`, `NOTION_SNS_DATABASE_ID`,
   `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN`을 저장한다.
4. `validate-config`를 통과시킨다.
5. `sync --backfill 10 --dry-run` 확인 후 `sync --backfill 10`을 한 번 실행한다.

## 일상 운영

- `초안`: 문구와 링크를 검토한다.
- `승인`: 자동 슬롯 배정과 게시를 허용한다.
- `보류`: 숫자·표현 검수 실패를 수정한 뒤 다시 동기화한다.
- `오류`: 인증, 권한, 네트워크 오류를 확인한 뒤 상태를 `승인`으로 되돌려 재시도한다.
- `게시중`이 장시간 남으면 `publish-due`를 수동 재실행한다. Harness는 최근 48시간 동일
  본문과 저장된 게시 ID를 대조한 뒤 누락된 구간부터 진행한다.

## 토큰과 장애

- 인증 오류가 나면 Meta에서 토큰 만료·권한·사용자 ID를 확인하고 GitHub Secret을 교체한다.
- 429/5xx는 세 번 자동 재시도한다. 계속 실패하면 Notion `오류`에 원인이 기록된다.
- Threads ID가 일부 저장된 연속 스레드는 해당 ID를 지우지 않는다.
- GitHub Actions 예약 실행은 지연될 수 있으므로 완료 시각이 슬롯에서 15분 이상 벗어나면
  Actions 상태와 Meta API 응답을 확인한다.
