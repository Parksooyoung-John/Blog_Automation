# MoneyBrief 기획·마케팅·SEO·성과분석 구현 인수인계

작성일: 2026-10-04 (Asia/Seoul)

## 목표

기존 `네이버 블로그 → OpenAI 초안/검수 → Notion 사람 승인 → Threads 예약 게시` 흐름은
유지하면서 다음 성장 퍼널을 추가한다.

```text
네이버 검색 수요 조사
→ 콘텐츠 기획·키워드 선정
→ Threads/블로그 초안 생성
→ 사람 승인
→ 게시
→ Threads 반응 + 블로그 수동 조회수 기록
→ 다음 주제·Hook·슬롯에 반영
```

공식 API만 자동 수집한다. 브라우저 로그인 자동화와 비공식 통계 크롤링은 금지한다.
Threads에서 네이버 블로그로 이동한 정확한 방문자 수는 측정할 수 없으므로 게시 시점 전후의
블로그 조회 변화는 반드시 `추정 유입`으로 표시한다.

## 작업 위치와 Git 상태

- 원본 저장소: `C:\Users\swims\OneDrive\Claude_code\블로그\블로그자동화`
- 구현에 사용할 깨끗한 작업트리:
  `C:\Users\swims\OneDrive\Claude_code\블로그\.worktrees\blog-link-ratio`
- 브랜치: `codex/blog-link-ratio`
- HEAD: `3a7b120 feat: raise blog link share to forty percent`
- 원격 브랜치: `origin/codex/blog-link-ratio`
- 작업트리는 이 문서 생성 전까지 깨끗했다.
- 원본 `main`은 사용자 변경과 콘텐츠 파일이 많이 섞인 dirty 상태이며
  `origin/main`보다 ahead 2 / behind 14이다. 원본 `main`에서 구현하거나 정리하지 말 것.
- `codex/blog-link-ratio`에는 최근 10개 블로그 콘텐츠 중 링크 비율을 30~40%로 유지하는
  변경이 이미 커밋·푸시되어 있다. 새 기능은 이 브랜치 위에 구현한다.

## 현재 확인된 코드 상태

- 패키지: `sns_harness/src/sns_harness`
- CLI 진입점: `src/sns_harness/__main__.py`
- Notion 어댑터: `src/sns_harness/queues/notion.py`
- Threads API: `src/sns_harness/publishers/threads.py`
- 모델·결정적 검수: `src/sns_harness/models.py`
- 현재 Notion 확장 스키마에는 콘텐츠유형, 게시슬롯, Hook유형, 블로그링크사용,
  운영메모, 자동생성여부, 사람수정필요, 중복검사키, 성과판정만 있다.
- `성과판정` 기본값만 존재하며 실제 metrics 수집·보고 CLI는 아직 없다.
- Threads 게시 검증과 Notion 승인 게이트는 기존 구현을 그대로 보존해야 한다.
- OpenAI 호출은 현재 Structured Output 기반이며 기존 Writer/Reviewer 계약을 깨지 않는다.

## 중단 지점

계획에 포함된 공식 Codex 스킬 설치를 시도했으나 사용자가 실행 중단했다. 아래 네 스킬은
현재 모두 설치되지 않았다.

- `jupyter-notebook`
- `define-goal`
- `gh-fix-ci`
- `security-best-practices`

다음 세션에서 설치가 필요하면 먼저 사용자에게 승인받아 아래 공식 설치기를 다시 실행한다.

```powershell
python C:\Users\swims\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py `
  --repo openai/skills `
  --path skills/.curated/jupyter-notebook `
         skills/.curated/define-goal `
         skills/.curated/gh-fix-ci `
         skills/.curated/security-best-practices
```

설치된 스킬은 다음 대화부터 사용할 수 있다고 안내한다.

## 구현 순서

### 1. 기준선 검증

깨끗한 작업트리의 `sns_harness`에서 먼저 실행한다.

```powershell
$python='C:\Users\swims\OneDrive\Claude_code\블로그\블로그자동화\sns_harness\.venv\Scripts\python.exe'
$env:PYTHONPATH=(Resolve-Path 'src').Path
& $python -m pytest -q
& $python -m ruff check src tests
```

기준선 실패가 있으면 새 기능과 섞지 말고 먼저 원인을 기록한다.

### 2. 프로젝트 전용 스킬

`skill-creator` 지침에 따라 `$CODEX_HOME/skills/moneybrief-growth-strategy`를 만든다.

스킬에 포함할 내용:

- 금융 주제 적합성·공식 근거 기준
- 검색의도: 정보확인, 조건비교, 신청방법, 계산, 주의사항
- 네이버 데이터랩은 상대 검색 추세로만 사용하고 절대 검색량·순위를 만들지 않는 규칙
- Hook·CTA·링크 비율 실험 규칙
- 성과판정과 다음 콘텐츠 추천
- 표본 부족 시 결론을 보류하는 규칙
- 승인 전 게시 금지와 비공식 크롤링 금지

README를 별도로 만들지 말고 `SKILL.md`, 필요한 경우 `references/`만 사용한다.
`quick_validate.py`로 검증한다.

### 3. 모델과 Notion 스키마

최소 모델을 추가한다.

- `SearchIntent`: 정보확인, 조건비교, 신청방법, 계산, 주의사항
- `TrendDirection`: 상승, 유지, 하락
- `Timeliness`: 상시, 계절, 마감임박
- `ContentGoal`: 도달, 댓글, 저장·공유, 블로그 유입
- `SampleStatus`: 충분, 부족, 미측정
- `TopicResearch`: 키워드·연관키워드·검색의도·트렌드·공식근거·점수·실험가설
- `PostMetrics`: 측정창, 조회·반응값, 블로그 수동 조회수, 측정출처·시각

Notion 속성은 기존 DB에 추가하며 수동 입력값을 자동 수집이 덮어쓰지 않게 분리한다.

- 기획키워드, 연관키워드, 검색의도
- 트렌드지수, 트렌드방향, 시의성
- 콘텐츠목표, 실험가설
- Threads조회수, 좋아요, 답글, 재게시, 인용공유, 팔로우증가
- 24시간조회수, 72시간조회수, 7일조회수
- 블로그조회수(수동), 추정블로그유입
- 측정출처, 표본상태, 성과확인시각

API가 지원하지 않거나 분모가 없는 값은 숫자 `0`이 아니라 비어 있음/`미측정`으로 저장한다.

### 4. 네이버 데이터랩 클라이언트와 주제 조사

새 모듈 예시: `src/sns_harness/research/naver_datalab.py`.

- 공식 endpoint `POST https://openapi.naver.com/v1/datalab/search`만 사용한다.
- 환경변수: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`.
- 키워드 그룹은 요청당 최대 5개로 분할한다.
- 상대 검색 추세만 반환하며 절대 검색량이나 검색 순위로 표현하지 않는다.
- 429·5xx·네트워크 오류만 제한 재시도한다.
- `research-topics --days 30 [--dry-run]` CLI를 추가한다.
- `--dry-run`은 Notion 쓰기 없이 계산 결과만 출력한다.

점수는 아래 고정 가중치로 계산한다.

- 채널 적합성 35%
- 검색 추세 25%
- 공식 근거 충실도 20%
- 최근 30일 중복도 10%
- Threads 대화 가능성 10%

공식 근거 부족, 일반 상품, 최근 제목·주제·검색의도 중복은 게시 후보로 만들지 않는다.

### 5. Threads 성과 수집

새 모듈 예시: `src/sns_harness/metrics/threads.py`와 `metrics/service.py`.

CLI:

```powershell
python -m sns_harness metrics collect --window 24h
python -m sns_harness metrics collect --window 72h
python -m sns_harness metrics collect --window 7d
python -m sns_harness metrics report --days 30
```

- 공식 Threads Graph API가 실제 제공하는 metric 이름을 구현 시점의 Meta 공식 문서로 다시
  확인한다. 기억으로 endpoint나 필드명을 만들지 않는다.
- 게시완료이며 Threads ID가 있는 항목만 수집한다.
- 동일 게시물·측정창은 idempotent update한다.
- 지원되지 않는 프로필 방문·팔로우 등은 `미측정`으로 둔다.
- 네이버 블로그 내부 조회수는 Notion의 수동 필드만 읽고 자동으로 수정하지 않는다.
- 추정 블로그 유입은 게시 전후 블로그 조회 차이와 시간창을 사용하되 항상 추정값으로 표시한다.

성과판정은 최근 30일 동일 콘텐츠 유형 중앙값과 비교한다.

- 도달·목표 행동 모두 중앙값 이상: `repeatable`
- 도달만 중앙값 이상: `reach-only`
- 목표 행동만 중앙값 이상: `conversion-candidate`
- 둘 다 미만: `underperforming`
- 측정 시간이나 표본 부족: `insufficient-data`

분석 축은 콘텐츠유형 × Hook유형 × 게시슬롯 × 블로그링크사용이다.

### 6. Promptfoo와 보고서

Promptfoo는 런타임 의존성으로 넣지 않는다. 별도 개발/CI 평가 구성으로 다음을 검사한다.

- 원문에 없는 숫자·혜택·기한
- 과장·공포·수익 보장 표현
- 제목/Hook 단순 반복
- 링크형/비링크형 CTA 계약
- 검색의도와 제목·본문 불일치

OpenAI 공식 문서 확인 결과 Structured Outputs는 JSON Schema를 강제할 수 있다. 기존
구조화 출력은 유지한다. OpenAI Evals 플랫폼은 2026년 종료 일정이 공지되어 있으므로 새
구현을 해당 Evals API에 종속시키지 말고 로컬 pytest/Promptfoo fixture를 우선한다.

월간 보고서는 우선 JSON과 Markdown으로 생성한다. XLSX가 필요할 때만 `spreadsheets` 스킬의
artifact_tool 지침에 따라 추가하고, Python openpyxl/pandas로 우회하지 않는다.

### 7. GitHub Actions

- 주제 조사: 하루 1회
- metrics 24h/72h/7d: 각 대상 측정창에 맞는 정기 실행
- 기존 게시 workflow와 concurrency를 공유하거나 충돌하지 않게 별도 read/update job으로 구성
- 로그에 본문·토큰·전체 상품 URL을 출력하지 않는다.
- 한 항목 실패가 다른 항목 수집을 막지 않게 항목별 격리하고 요약에 checked/updated/
  unmeasured/failed를 기록한다.

### 8. Archify 문서 갱신

기존 `docs/architecture/sns-harness.architecture.json`을 새로 만들지 말고 업데이트한다.
네이버 데이터랩 → Topic Research → Notion 기획/승인 → Threads → Metrics → 성과판정 피드백
루프를 추가한다. Archify 지침대로 validate → deliver → visual-check를 수행하고 생성 HTML과
검증 영수증을 함께 확인한다.

## 테스트 목록

- 데이터랩 페이지/그룹 분할과 추세 계산
- 상대 지수를 절대 검색량이나 순위로 오인하지 않음
- 동일 검색의도·제목의 30일 중복 차단
- 근거 없는 주제 후보 제외
- 24h/72h/7d 측정창 분리
- API 미지원·분모 0은 `미측정`
- 수동 블로그조회수를 자동 수집이 덮어쓰지 않음
- 동일 Threads ID·측정창 중복 집계 방지
- 중앙값 기반 5개 성과판정
- 표본 부족 시 `insufficient-data`
- dry-run 외부 쓰기 없음
- 승인 전 게시 금지·기존 부분 게시 복구 회귀 테스트
- GitHub Actions YAML 파싱
- 전체 pytest와 Ruff 통과

## 완료 조건

- `research-topics --days 30`이 공식 데이터랩 결과로 후보를 산출한다.
- metrics CLI 4개가 동작하며 측정 불가 값을 거짓 `0`으로 저장하지 않는다.
- Notion에서 기획 근거, 목표, 24h/72h/7d 성과와 표본상태를 확인할 수 있다.
- 월간 보고서가 콘텐츠유형·Hook·슬롯·링크 여부를 비교한다.
- 네이버 수동 조회수와 자동 Threads 지표가 서로 덮어쓰지 않는다.
- 기존 승인·예약·게시 안전 경계가 유지된다.
- 전체 테스트, Ruff, workflow 검사가 통과한다.

## 제외 사항

- Umami, Plausible, PostHog, Langfuse 도입
- 별도 랜딩페이지나 소유 도메인 구축
- Google Search Console·GA4 연결
- 네이버 통계 화면 크롤링
- 개인 단위 Threads→블로그 추적
- AI가 검색량·CTR·순위 또는 공식 근거를 추정하는 기능

