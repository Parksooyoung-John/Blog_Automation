# Blog Automation

Claude AI 에이전트팀이 콘텐츠를 생성하고, Playwright가 Tistory에 자동 발행하는 반자동 블로그 자동화 시스템.

## 전체 워크플로우

```
Claude Code에서 /content-repurposer 실행
          ↓ (에이전트 5명 협업)
_workspace/02_blog_post.md 생성
          ↓
python 04_notion_upload.py
  · 마크다운 → HTML 변환
  · 이미지 플레이스홀더 → Pexels / DALL-E 자동 교체
  · Notion DB "발행대기" 업로드
          ↓
python 03_tistory_playwright.py
  · Notion "발행대기" 항목 감지
  · DALL-E 썸네일 생성
  · 쿠팡 파트너스 링크 삽입
  · Playwright로 Tistory 자동 발행
  · Notion 상태 → "발행완료"
```

## 파일 구조

```
.
├── .claude/
│   ├── agents/
│   │   ├── source-analyst.md       # 원본 분석가
│   │   ├── blog-writer.md          # 블로그 작가 (SEO 최적화)
│   │   ├── sns-copywriter.md       # SNS 카피라이터
│   │   ├── presentation-builder.md # 프레젠테이션 빌더
│   │   └── quality-reviewer.md     # 품질 검증자
│   └── skills/
│       ├── content-repurposer/     # 오케스트레이터 스킬
│       ├── content-atomization/    # 원자화 방법론
│       └── platform-adaptation/    # 플랫폼 적응 방법론
├── 03_tistory_playwright.py        # Notion → Tistory 자동 발행
├── 03_post_processor.py            # 발행 후 썸네일/링크 후처리
├── 04_notion_upload.py             # 블로그 포스트 → Notion 업로드
├── .env.example                    # 환경변수 템플릿
└── requirements.txt
```

## 설치

```bash
pip install -r requirements.txt
playwright install chromium
```

## 환경변수 설정

`.env.example`을 복사해서 `.env`로 저장 후 실제 값 입력:

```bash
cp .env.example .env
```

| 변수 | 설명 | 필수 |
|------|------|------|
| `TISTORY_KAKAO_EMAIL` | 카카오 로그인 이메일 | ✅ |
| `TISTORY_KAKAO_PASSWORD` | 카카오 로그인 비밀번호 | ✅ |
| `TISTORY_BLOG_NAME` | 블로그명 (`xxx`.tistory.com) | ✅ |
| `NOTION_API_KEY` | Notion 통합 키 | ✅ |
| `NOTION_DATABASE_ID` | Notion DB ID | ✅ |
| `OPENAI_API_KEY` | DALL-E 썸네일 생성용 | ✅ |
| `PEXELS_API_KEY` | 본문 이미지 검색 (없으면 DALL-E 대체) | ❵ |
| `COUPANG_PARTNER_ID` | 쿠팡 파트너스 ID | ❵ |

## 사용법

### 1. 콘텐츠 생성 (Claude Code)

Claude Code를 프로젝트 디렉토리에서 열고 스킬 실행:

```
/content-repurposer
```

원본 콘텐츠(기사, 스크립트, URL 등)를 붙여넣으면 에이전트 5명이 협업하여 생성:
- `_workspace/01_source_analysis.md` — 원본 분석
- `_workspace/02_blog_post.md` — SEO 최적화 블로그 포스트 ← Tistory 발행 대상
- `_workspace/03_sns_package.md` — SNS 멀티 플랫폼 포스트
- `_workspace/04_presentation.md` — 프레젠테이션 슬라이드
- `_workspace/05_review_report.md` — 품질 검증 리포트

### 2. Notion 업로드

```bash
python 04_notion_upload.py
```

`_workspace/02_blog_post.md`를 읽어 Notion DB에 "발행대기" 상태로 저장.  
이미지 플레이스홀더는 Pexels → DALL-E 순으로 자동 교체.

### 3. Tistory 발행

```bash
python 03_tistory_playwright.py
```

Notion "발행대기" 항목을 감지해 Tistory에 자동 발행.

## 에이전트팀 구조

```
source-analyst (원본 분석)
       ↓
┌──────┼──────┐
blog-  sns-   presentation-
writer copy-  builder
       writer
└──────┼──────┘
       ↓
quality-reviewer (교차 검증)
```

## 콘텐츠 품질 시스템

### blog-writer 작성 흐름 (의무)

글 작성 전 아래 3가지를 먼저 선언한 뒤 본문을 시작한다:

1. **글 유형** 선택 — 정책이슈형 / 독자영향형 / 비교판단형 / 누적허브형
2. **핵심 메시지 1문장** — 독자가 가져갈 단 1가지
3. **첫 문단 각도** — "왜 지금 이 글인지" 구어체 초안

### 글 유형별 제목 템플릿

| 유형 | 템플릿 | 예시 |
|------|--------|------|
| 정책이슈형 | `[키워드] [변화], [독자가 확인할 것]` | "5세대 실손보험 출시, 1~4세대 가입자가 갈아타기 전 확인할 5가지" |
| 독자영향형 | `[조건/상황] — [행동 가이드]` | "자동차보험 갱신 전 보험료 줄이는 할인 특약 10가지" |
| 비교판단형 | `[A] vs [B], [판단 기준]` | "방산 ETF vs 조선 ETF, 순환매 기대감에 확인할 체크포인트" |

**제목 후보 2개 생성 → 더 구체적인 것 선택** (후보 없이 확정 금지)

**제목 금지 패턴**: "완전 정리/총정리" 단독 사용 · "~하는 법" 단독 종결 · "지금 바로 ~해야 하는 이유"

### quality-reviewer 검증 기준

| 항목 | 기준 |
|------|------|
| 제목 유형별 템플릿 준수 | 🔴 필수 |
| 첫 문단 "왜 지금" 배경 설명 | 🔴 필수 |
| 체크리스트(`- [ ]`) 포함 | 🔴 필수 |
| 서론 구어체 시작 | 🔴 필수 |
| 본문 내 개인 경험/주변 사례 | 🔴 필수 |
| 결론에 작성자 의견 포함 | 🔴 필수 |
| AI 정형화 표현 2회 미만 | 🔴 필수 |
| 투자 권유·수익 보장 표현 금지 | 🔴 필수 |

## 이미지 처리 방식

본문 이미지는 `blog-writer`가 생성한 플레이스홀더를 기반으로 자동 교체:

1. **Pexels** (무료) — 키워드 기반 스톡 사진 검색
2. **DALL-E 3** (폴백) — AI 일러스트 생성 (~$0.04/장)
3. **생략** — 두 방법 모두 실패 시 플레이스홀더 제거

썸네일(대표이미지)은 DALL-E 3가 제목 기반으로 항상 생성.

## API 키 발급

- **Notion API**: [notion.so/my-integrations](https://www.notion.so/my-integrations)
- **OpenAI API**: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **Pexels API**: [pexels.com/api](https://www.pexels.com/api/) (무료)
- **쿠팡 파트너스**: [partners.coupang.com](https://partners.coupang.com)
