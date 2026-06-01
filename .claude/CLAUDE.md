# Content Repurposer Harness

1개 원본 콘텐츠를 블로그·SNS·뉴스레터·프레젠테이션·스크립트로 다중 변환하는 에이전트 팀 하네스.

## 구조

```
.claude/
├── agents/
│   ├── source-analyst.md        — 원본 분석가 (구조 분석, 핵심 추출, 변환 전략)
│   ├── blog-writer.md           — 블로그 작가 (SEO 최적화 블로그 포스트)
│   ├── sns-copywriter.md        — SNS 카피라이터 (플랫폼별 포스트)
│   ├── presentation-builder.md  — 프레젠테이션 빌더 (슬라이드 구성)
│   └── quality-reviewer.md      — 품질 검증자 (교차 검증, 메시지 일관성)
├── skills/
│   ├── content-repurposer/
│   │   └── skill.md             — 오케스트레이터 (팀 조율, 워크플로우, 에러핸들링)
│   ├── platform-adaptation/
│   │   └── skill.md             — sns-copywriter+blog-writer 확장 (플랫폼별 DNA, 변환 매트릭스)
│   └── content-atomization/
│       └── skill.md             — source-analyst+presentation-builder 확장 (MINE 분석, 원자 분류)
└── CLAUDE.md                    — 이 파일
```

## 사용법

`/content-repurposer` 스킬을 트리거하거나, "이 콘텐츠 리퍼포징해줘" 같은 자연어로 요청한다.

## 산출물

모든 산출물은 `_workspace/` 디렉토리에 저장된다:
- `00_input.md` — 사용자 입력 정리
- `01_source_analysis.md` — 원본 분석 보고서
- `02_blog_post.md` — 블로그 포스트
- `03_sns_package.md` — SNS 포스트 패키지
- `04_presentation.md` — 프레젠테이션 슬라이드
- `05_review_report.md` — 리뷰 보고서

---

## 내부 링크 시스템 — 함께 읽으면 좋은 글

### 목적
블로그 체류 시간 증가 + 관련 포스트 유입 유도. 독자가 연관 글로 자연스럽게 이동.

### 파일
`C:\Users\swims\OneDrive\Claude_code\블로그\블로그자동화\_posts_index.md`
- 발행된 모든 포스트의 제목·URL·카테고리·키워드를 관리하는 인덱스
- blog-writer가 내부 링크 생성 시 이 파일을 참조
- 새 포스트 발행 후 반드시 추가 (content-repurposer Phase 4)

### blog-writer 동작 규칙
1. 작업 시작 전 `_posts_index.md` 읽기
2. 현재 포스트와 같은 카테고리 또는 키워드가 겹치는 기발행 포스트 최대 3개 선택
3. 본문 마지막(공식 출처 표 위)에 삽입

### 필수 출력 형식
```
---

## 함께 읽으면 좋은 글

- [[포스트 제목]](https://j2gblog.tistory.com/숫자)
- [[포스트 제목]](https://j2gblog.tistory.com/숫자)
```

### 인덱스 업데이트 규칙
새 포스트 Tistory 발행 완료 → `_posts_index.md`에 행 추가:
```
| 제목 | URL | 카테고리 | 키워드 |
```

---

## 금융 콘텐츠 팀 규칙

> 금융 주제(대출·세금·연금·보험·주식·전세 등) 포스팅 시 **팀 전체**가 따르는 규칙이다.

### blog-writer 의무 사항
본문 최상단에 업데이트 날짜·주의 문구, 본문 최하단에 공식 출처 표를 반드시 삽입한다:

```
> 📅 최종 업데이트: YYYY년 MM월 DD일
> ⚠️ 주의: 정책과 금리는 변경될 수 있습니다. 신청 전 공식 사이트를 확인하세요.
```

```
## 공식 출처 및 참고
| 기관 | 내용 | 링크 |
|------|------|------|
| 기관명 | 확인 가능한 정보 | 공식 URL |
> 이 글의 수치는 [기준일] 기준입니다.
```

### source-analyst 의무 사항
분석 보고서에 **수치 기준일**과 **출처 기관**을 명시한다. blog-writer에게 전달할 때 금융 콘텐츠 여부를 플래그로 표시한다.

### quality-reviewer 의무 사항
금융 콘텐츠 검증 체크리스트에 다음 항목을 추가한다:
- [ ] 업데이트 날짜·주의 문구가 최상단에 있는가?
- [ ] 공식 출처 표가 최하단에 있는가?
- [ ] 출처 URL이 실제 공식 기관 링크인가?
- [ ] 수치에 기준일이 명시되어 있는가?

### 주요 금융 기관 공식 URL
| 기관 | URL | 용도 |
|------|-----|------|
| 주택도시기금 | nhuf.molit.go.kr | 버팀목·청년전세대출 |
| 주택도시보증공사(HUG) | hug.go.kr | 전세보증·분양보증 |
| 한국주택금융공사(HF) | hf.go.kr | 보금자리론·전세보증 |
| 서울보증보험(SGI) | sgi.co.kr | SGI 전세보증 |
| 국세청 홈택스 | hometax.go.kr | 세액공제·연말정산 |
| 금융감독원 | fss.or.kr | ISA·IRP·연금저축 |
| 복지로 | bokjiro.go.kr | 청년 정부지원금 |

---

## 발행 파이프라인

```
/content-repurposer 실행
    ↓ (에이전트 5명)
_workspace/02_blog_post.md 생성
    ↓
python -X utf8 04_notion_upload.py
    ↓ (마크다운 → HTML + 카테고리/태그 자동 분류 + Notion 업로드)
Notion DB 항목 (상태: "발행대기")
    ↓
python -X utf8 03_tistory_playwright.py
    ↓ (Playwright 브라우저 자동화)
Tistory 공개 발행
```

---

## 파이프라인 기술 노트 — 알려진 이슈 & 해결책

> 이 섹션은 실제 디버깅을 통해 확인한 문제와 해결책이다.
> `03_tistory_playwright.py`, `04_notion_upload.py` 수정 시 반드시 참조할 것.

---

### [Notion API] 블록 페이지네이션

**문제**: `GET /v1/blocks/{id}/children`는 기본 100개만 반환. 긴 포스트(3350개 블록)는 첫 100개만 가져와 내용 잘림.

**해결**: `has_more` + `next_cursor` 루프로 전체 수집:
```python
url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
while url:
    data = requests.get(url, headers=NOTION_HEADERS).json()
    # ... 블록 처리 ...
    url = (f"...?page_size=100&start_cursor={data['next_cursor']}"
           if data.get("has_more") else None)
```

---

### [Tistory] base64 이미지 → 발행 실패 (무증상)

**문제**: DALL-E 생성 이미지가 base64 data URI로 저장되면 HTML이 6MB+가 됨. Tistory 제출 크기 한도 초과 시 오류 없이 발행이 조용히 실패함. 포스트가 저장되지 않거나 비공개로 저장됨.

**해결**: `_strip_base64_images()` — `<figure>` 블록 중 `data:image/`가 포함된 것만 제거. Pexels URL 이미지는 보존:
```python
def _strip_base64_images(html: str) -> str:
    # '<figure' ~ '</figure>' 범위에서 'data:image/' 포함 블록 제거
    ...
```

**적용 위치**: `get_script_content()` — HTML 감지 후 즉시 적용.

---

### [Tistory] 태그 입력 — Playwright locator 실패

**문제**: `input[name="tagText"]`(placeholder="태그입력", class="tf_g")가 DOM에 존재하고 visible=True이지만, Playwright `page.locator(...).click()`이 30초 타임아웃. `force=True`도 동일하게 실패. 원인 미상(프레임 격리 또는 포인터 이벤트 처리 방식 차이 추정).

**해결**: JS `focus()` 후 `page.keyboard.type()`으로 입력:
```python
focused = page.evaluate(
    "() => { const el = document.querySelector('input[name=\"tagText\"]'); "
    "if (!el) return false; el.focus(); return true; }"
)
if focused:
    for tag in tags:
        page.keyboard.type(tag)
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
```

**타이밍**: "완료" 버튼 클릭(발행 패널 오픈) **이전** 에디터 화면에서 입력해야 함.

---

### [Tistory] 카테고리 선택 — ReactModal 오버레이 가로막힘

**문제**: 발행 패널이 `ReactModal__Overlay`(전체화면 오버레이)로 렌더링됨. 패널 내부의 카테고리 버튼(`id="category-btn"`, `role="combobox"`)을 Playwright locator로 클릭하면 오버레이가 pointer event를 가로채 실패.

**DOM 구조**:
```
#category-btn [role=combobox, aria-controls="category-list"]
  → 드롭다운 열림 →
#category-list [role=listbox]
  → li [role=option] 텍스트가 카테고리명
```

**해결**: JS `dispatchEvent`로 combobox 열기 + Playwright `get_by_role("option")`으로 선택:
```python
page.evaluate("""
    () => {
        const btn = document.getElementById('category-btn');
        btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
    }
""")
page.wait_for_timeout(800)
page.get_by_role("option", name=category_name).click(timeout=3000)
```

**주의**: TinyMCE 에디터도 "선택 안 함" 버튼(disabled)을 갖고 있어 `get_by_role("button", name="선택 안 함")`은 disabled 버튼에 걸림. `#category-btn` ID를 직접 사용할 것.

---

### [Tistory] 대표이미지(썸네일) 업로드

**문제**: "대표이미지 추가" span 클릭이 `input[type="file"]`에 가로막혀 파일 선택 다이얼로그 미트리거. `expect_file_chooser()` 방식도 실패.

**해결**: 패널 오픈 후 `set_input_files()` 직접 호출:
```python
page.locator('input[type="file"][accept="image/*"]').first.set_input_files(
    thumb_path, timeout=5000
)
```

**타이밍**: "완료" 버튼 클릭 → 패널 렌더링 대기(2500ms) **후** 업로드.

---

### [Tistory] 공개 라디오 버튼

**문제**: 발행 패널의 공개/비공개 라디오는 React 커스텀 컴포넌트. 실제 `<input type="radio">`가 있지만 CSS로 숨겨져 있고, 레이블 클릭도 Playwright에서 "not visible" 오류.

**해결**: JS TreeWalker로 visible 텍스트 노드 "공개"를 찾아 부모 요소(`SPAN.checkbox-text`) 클릭:
```python
page.evaluate("""
    () => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while (node = walker.nextNode()) {
            if (node.textContent.trim() === '공개') {
                const el = node.parentElement;
                if (el && el.offsetParent !== null) { el.click(); return; }
            }
        }
    }
""")
```

**주의**: "공개" 클릭 후 발행 버튼이 "발행" → **"공개 발행"** 으로 텍스트가 바뀜. `get_by_role("button", name="공개 발행")`으로 클릭.

---

### [Tistory] HTML 콘텐츠 감지 — 04_notion_upload.py 경로

**조건**: `04_notion_upload.py`가 저장한 Notion 블록은 이미 HTML. 이 경우 GPT 제목 생성 스킵 + base64 제거만 적용.

**판별 로직**:
```python
stripped = raw_text.strip()
if stripped.startswith('<'):
    return "", _strip_base64_images(stripped)
# 아래는 Make.com 원문 텍스트 경로 (GPT 제목 생성 등)
```

**제목**: HTML 경로에서는 Notion 행의 `이름` 프로퍼티 값을 그대로 사용.

---

### [04_notion_upload.py] 카테고리 자동 분류 + Notion select 쉼표 제한

**제약**: Notion select 옵션명에 쉼표(`,`) 사용 불가 — API가 `validation_error` 반환.

**구조**: Notion 저장명(쉼표 없음) / Tistory 표시명(쉼표 허용)을 분리:

```python
# 04_notion_upload.py: CATEGORY_RULES — Notion 저장명 (쉼표 없음)
CATEGORY_RULES = [
    (["ISA", "IRP", "연금", "절세"], "절세연금"),       # ← Notion에 저장되는 이름
    (["대출", "금리"],               "대출금리"),
    (["주식", "ETF"],                "주식ETF"),
    (["ChatGPT", "Claude"],          "소프트웨어 비교"), # 원래 쉼표 없음 → 그대로
    ...
]

# 03_tistory_playwright.py: TISTORY_CATEGORY_MAP — 실제 Tistory 카테고리명으로 변환
TISTORY_CATEGORY_MAP = {
    "절세연금":     "절세, 연금",
    "대출금리":     "대출, 금리",
    "주식ETF":      "주식, ETF",
    "AI부업수익화": "AI 부업, 수익화",
}
```

**사용 흐름**: `CATEGORY_RULES`로 Notion 저장 → `TISTORY_CATEGORY_MAP.get(notion_cat, notion_cat)`로 Tistory 카테고리명 변환.

Tistory 카테고리 추가/변경 시 두 파일 모두 동기화할 것.

---

### [공통] 환경변수 (.env)

| 변수명 | 용도 |
|--------|------|
| `NOTION_API_KEY` | Notion API 인증 |
| `NOTION_DATABASE_ID` | 발행 관리 DB ID |
| `OPENAI_API_KEY` | DALL-E 썸네일 + GPT 제목 생성 |
| `PEXELS_API_KEY` | Pexels 이미지 검색 (선택) |
| `TISTORY_KAKAO_EMAIL` | 카카오 로그인 이메일 |
| `TISTORY_KAKAO_PASSWORD` | 카카오 로그인 비밀번호 |
| `TISTORY_BLOG_NAME` | 블로그명 (예: j2gblog) |
