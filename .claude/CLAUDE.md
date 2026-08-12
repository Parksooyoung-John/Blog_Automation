# Content Repurposer Harness

1개 원본 콘텐츠를 블로그·SNS·뉴스레터·프레젠테이션·스크립트로 다중 변환하는 에이전트 팀 하네스.

> 🔴 **애드센스 재도전 진행 중** — 작업 시작 전 [`ADSENSE_PROGRESS.md`](../ADSENSE_PROGRESS.md)를 먼저 읽을 것.
> 4차 거절("가치가 별로 없는 콘텐츠") 대응 중이며, 현재 **Phase 0 완료 / Phase 1(하네스 규칙 수술) 대기** 상태다.
> 진단 결과 **획일성이 blog-writer.md 규칙 자체에서 생산되고 있으므로**, 개별 포스트만 고치는 대응은
> 이미 3번 실패했다. 규칙을 먼저 고친 뒤 콘텐츠를 손댈 것.

## 모델 사용 정책 (비용 최적화)

### Pro Plan vs 추가 크레딧 기준
- Pro Plan 세션이 활성 상태이면 최우선 사용한다
- 추가 크레딧 사용은 Pro 세션 소진 후에만 허용한다
- 작업 시작 전 `/compact` 실행으로 컨텍스트를 최소화한다

### 서브에이전트 모델 할당
| 에이전트 | 모델 | 근거 |
|---------|------|------|
| source-analyst | claude-haiku-4-5 | 분석·추출, 롱폼 생성 불필요 |
| blog-writer | claude-sonnet-4-5 | 발행 품질 직결, 2000자+ 구조화 문서 |
| sns-copywriter | claude-haiku-4-5 | 숏폼·카피, 복잡도 낮음 |
| presentation-builder | claude-haiku-4-5 | 구조 설계, 패턴 반복 |
| quality-reviewer | claude-haiku-4-5 | 체크리스트 검증, 판단 작업 |

### 실행 모드별 에이전트 수 (토큰 절감)
- **블로그 전용** (기본): source-analyst + blog-writer + quality-reviewer = **3명**
- **풀 리퍼포징** (명시 시만): 5명 전원
- 사용자가 "SNS", "프레젠테이션", "슬라이드", "리퍼포징"을 명시하지 않으면 블로그 전용 모드로 실행한다

### 비용 절감 규칙
- 새 작업 시작 전 `/clear` 실행
- 컨텍스트 길어지면 `/compact` 실행
- 서브에이전트는 최소 수만큼만 spawn한다
- 이미지 생성은 대표이미지 1장만 (04_notion_upload.py에서 처리)

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
3. **`thumb: pending`인 포스트는 카드 후보에서 제외** — 실제 CDN URL이 있는 포스트만 사용
4. 본문 마지막(공식 출처 표 위)에 삽입
5. **내부 링크는 항상 데스크톱 숫자 URL(`https://j2gblog.tistory.com/{번호}`)만 사용** — `/m/{번호}`(모바일 대체 URL), `/{번호}/comments`(댓글 뷰)로 링크하지 않는다. 두 URL 모두 Tistory가 자동 생성하며 canonical이 숫자 URL을 가리키는 정상 페이지이지만, 콘텐츠 자체는 숫자 URL과 동일하므로 내부 링크 대상이 아니다(2026-07-17, GSC 색인 실패 조사에서 확인).

> ⚠️ **anti-pattern**: `thumb: pending` 포스트를 카드로 사용하면 모든 카드에 같은 (잘못된) 이미지가 표시된다.
> 발행 완료 즉시 OG 이미지 URL을 가져와 인덱스를 업데이트해야 다음 포스트에서 카드가 정상 표시된다.

### 인덱스 썸네일 업데이트 — 발행 후 즉시 수행 (영구 호스팅, 2026-08-03부터)

> **배경**: Tistory og:image(daumcdn 서명 URL)는 계정 단위로 약 1개월마다 일괄 만료되어
> 사이트 전체 내부링크 카드가 동시에 깨지는 문제가 반복됐다(`thumb_host.py` 도입 전 이력은
> 아래 "[내부 링크 카드] 썸네일 URL 만료" 섹션 참조). 2026-08-03 `thumb_host.py` +
> `migrate_thumbs_permanent.py` 도입 이후로는 **썸네일을 한 번 다운로드해 이 저장소
> (`assets/thumbnails/`)에 커밋하고 jsdelivr CDN으로 서빙** — 만료가 없다. 새 포스트도
> 반드시 이 방식을 따를 것 (예전 `get_og.py` raw-URL 저장 패턴으로 되돌아가지 말 것).

Tistory 발행 완료 → `thumb_host.py`로 og:image를 다운로드·압축해 영구 URL을 받아
`_posts_index.md`의 `thumb` 필드에 저장한다:

```bash
python -X utf8 -c "
import requests, re
from thumb_host import host_thumb

post_id = '{번호}'
url = f'https://j2gblog.tistory.com/{post_id}'
r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
m = re.search(r'property=\"og:image\"\s+content=\"([^\"]+)\"', r.text)
if not m:
    m = re.search(r'content=\"([^\"]+)\"\s+property=\"og:image\"', r.text)
og = m.group(1) if m else None
print(host_thumb(post_id, og) if og else 'OG NOT FOUND')
"
```

출력된 `https://cdn.jsdelivr.net/gh/Parksooyoung-John/Blog_Automation@main/assets/thumbnails/{번호}.jpg`를
`thumb:` 필드에 그대로 저장한다. **`assets/thumbnails/{번호}.jpg`가 git에 커밋·푸시되기 전까지는
jsdelivr가 서빙하지 못하므로, 이 스크립트 실행 후 반드시 `assets/thumbnails/` 를 커밋·푸시할 것.**

**다음 포스트 배치 작성 전 `_posts_index.md`에 `thumb: pending`이나 `daumcdn` 원본 URL이 남아있지 않은지 확인할 것.**

### 필수 출력 형식 (HTML 카드)
```html
---

## 함께 읽으면 좋은 글

<div style="border:1px solid #e8e8e8;border-radius:12px;overflow:hidden;margin:16px 0;max-width:640px;">
<a href="URL" target="_blank" rel="noopener" style="display:flex;text-decoration:none;color:inherit;">
<div style="width:160px;min-width:160px;overflow:hidden;"><img src="THUMB" style="width:100%;height:105px;object-fit:cover;display:block;" /></div>
<div style="padding:14px 18px;flex:1;">
<div style="font-weight:700;font-size:15px;color:#333;margin-bottom:6px;">제목</div>
<div style="font-size:13px;color:#666;">설명</div>
<div style="font-size:12px;color:#aaa;margin-top:10px;">j2gblog.tistory.com</div>
</div></a></div>
```

### 인덱스 업데이트 규칙
새 포스트 Tistory 발행 완료 → `_posts_index.md`에 행 추가:
```
| 제목 | URL | 카테고리 | 키워드 |
```

**추가 필수**: `_posts_index.md`의 각 포스트 항목에는 `thumb:` 필드가 있다. 발행 직후 OG 이미지 URL을 확인하여 `pending`을 실제 URL로 교체할 것. `thumb: pending`인 채로 남겨두면 다음 포스팅에서 이 포스트를 내부 링크 카드로 사용할 수 없다.

---

## 블로그 포스팅 공통 작성 규칙

모든 포스트에 아래 규칙을 적용한다. **blog-writer.md에 상세 규칙이 있으며 이 요약과 함께 참조한다.**

### 애드센스 Low value 대응 (blog-writer 규칙 15~18) — 2026-08-06 대폭 개정

> 4차 거절 사유: "가치가 별로 없는 콘텐츠". 정책·상품 **요약만 하는 글은 발행 불가**.
> 진행 상황·진단 근거는 [`ADSENSE_PROGRESS.md`](../ADSENSE_PROGRESS.md) 참조.

**핵심 인식**: 획일성은 규칙 위반이 아니라 **규칙 준수의 결과**였다.
훅 문장·감정 주석 예시가 하드코딩돼 있어 에이전트가 그대로 복사했고,
`## 마무리`가 포맷에 리터럴로 박혀 초안 88%가 동일해졌다. 개별 글만 고치면 계속 재생산된다.

- **분량(규칙 17)**: 본문 **3,000자+**, **H2 5~7개**, **섹션당 400자+**. 제출 전 직접 세어 보고
- **마지막 H2**: `## 마무리`·`## 결론` 금지 — 주제어를 넣은 고유 표현
- **가공 인물 금지(규칙 2)**: "35세 직장인 A씨" 서사 폐지 → 조건 기반 계산 또는 운영자 검증 경험
- **체크리스트(규칙 5)**: 전 포스트 의무 폐지 → 절차·서류·자격요건일 때만, 배치당 1편
- **훅 문장(규칙 12)**: 템플릿 문장 폐지 → "담아야 할 정보"만 규정. 금지 문구 목록 준수
- **감정 주석(규칙 11)**: 예시 복사 금지 — 그 글 내용이 담긴 문장을 새로 쓸 것
- **메타 디스크립션**: "정리했습니다" 종결 금지 — 그 글만의 수치·결론 포함
- **제목**: `확인할 N가지`·`체크리스트`·`완전 정리`·em dash는 배치당 각 1편
- **E-E-A-T(규칙 18)**: 확인 경로 본문 명시 + 저자 박스 삽입
- **📅/⚠️ 블록쿼트 위치**: 본문 최상단 ❌, 도입부 다음도 ❌, 첫 H2 직전도 ❌ →
  **본문 맨 아래, 마무리 면책 문구 바로 위**(v3 확정, 라이브 109개 전부 이 위치)
- 독창적 해석 3요소 중 2개 이상(규칙 15) / 공식 통계 1개+ 기준일(규칙 16) / 표 아래 해석 문단
- H2 아이콘 최대 30% / 명령투 "확인하세요" 글당 2회 이하

### 표현 제한 (위반 시 재작성)
- 과장된 수익 보장 금지: "확실히 돈 번다", "반드시 수익", "무조건 유리" 등 단정 불가
- 특정 상품 가입 유도 금지: "지금 바로 가입", "이 카드를 추천합니다" 등 불가
- 중립 표현 사용: "확인해보세요", "비교해보세요"

### 공식 출처 URL — 클릭 가능한 링크 필수
```
✅ 올바른 예: [국세청 홈택스](https://www.hometax.go.kr)
❌ 잘못된 예: hometax.go.kr (클릭 불가 텍스트)
```

### 메타 정보 — 모든 포스트 필수
메타 디스크립션(155자), 태그(10개 내외), 카테고리, 예상 읽기 시간 — 누락 시 재작성

### 대표 이미지 프롬프트 — 항상 파일 끝에 포함
```
[THUMBNAIL_PROMPT]
영어 DALL-E 프롬프트, 16:9 ratio, no text
[/THUMBNAIL_PROMPT]
```
04_notion_upload.py가 자동 제거하므로 본문에는 노출되지 않음

### AI 콘텐츠 안내 문구 (ChatGPT·Claude·AI 도구 관련 글)
```
가격과 기능은 변경될 수 있습니다. 결제 전 공식 요금제 페이지를 확인하세요.
- ChatGPT: openai.com/pricing
- Claude: claude.ai/pricing
```

---

## 금융 콘텐츠 팀 규칙

> 금융 주제(대출·세금·연금·보험·주식·전세 등) 포스팅 시 **팀 전체**가 따르는 규칙이다.

### blog-writer 의무 사항
**본문 맨 아래, 마무리 면책 문구(`⚠️ 이 글의 수치는…`) 바로 위**에 업데이트 날짜·주의 문구를,
그 아래에 공식 출처 표를 반드시 삽입한다:

```
> 📅 최종 업데이트: YYYY년 MM월 DD일
> ⚠️ 주의: [이 글 주제에 맞는 변경 가능성 1문장]

> ⚠️ 이 글의 수치는 YYYY년 MM월 기준이며 … (마무리 면책 문구)
```

즉 본문 마지막 H2 섹션이 끝난 뒤 **공지 블록쿼트 → 면책 블록쿼트 → (내부링크 카드) →
공식 출처 표 → 저자 박스** 순서다. 두 블록쿼트가 나란히 붙어 "메타 정보" 묶음을 이룬다.

> ⚠️ **최상단·본문 중간에 넣지 말 것 (v1→v3, 2026-08-08 사용자 확정).** Tistory 홈 목록
> 발췌문이 본문 맨 앞을 가져가므로, 최상단에 두면 홈 글 목록 8개가 전부 같은 문구로 시작한다 —
> 애드센스 심사관이 보는 첫 화면이 보일러플레이트 반복이 되어 대량 생성 사이트로 읽힌다.
> v1("도입부 첫 문단 다음")·v2("도입부 전체 다음, 첫 H2 직전") 둘 다 실제 발행글에서
> 확인해보니 도입부와 본문 사이에 끼어 흐름을 끊었다(사용자가 스크린샷으로 두 번 지적).
> **최종 확정은 v3 — 본문 맨 아래**이며, 라이브 109개 전부 이 위치로 통일돼 있다.
> 새 글도 반드시 v3를 따를 것(어긋나면 사이트 전체 일관성이 깨진다).
> ⚠️ 문구도 매번 같게 복사하지 말 것.

출처 표 하단에 반드시 추가:
```
공식 출처 최종 확인일: YYYY년 MM월 DD일(게시일)
정책과 상품 조건은 변경될 수 있으므로 신청 전 공식 사이트를 확인하세요.
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

## 쿠팡파트너스 링크 연동

블로그 포스팅 요청 시 쿠팡파트너스 링크를 함께 제공하면 포스트에 자동 삽입된다.

### 사용법
요청 메시지에 링크를 포함하면 된다:
```
"[주제] 포스팅해줘. 쿠팡파트너스 링크: https://link.coupang.com/a/XXXXX (상품명: OOO)"
```
상품명은 선택. 없으면 "상품"으로 대체.

### 자동 처리 흐름
1. **content-repurposer** Phase 1: `link.coupang.com` URL 감지 → `00_input.md`에 저장
2. **blog-writer**: `00_input.md`의 `## 쿠팡파트너스` 섹션 확인 → CTA 버튼 + 공시 문구 삽입

### 포스트 내 출력 결과

**CTA 버튼** — 해당 상품 설명 섹션 바로 아래:
```html
<div style="text-align:center;margin:32px 0;">
  <a href="https://link.coupang.com/a/XXXXX" target="_blank" rel="nofollow sponsored"
     style="display:inline-block;background:#ee2222;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:16px;">
    🛒 쿠팡에서 [상품명] 확인하기
  </a>
</div>
```

**파트너스 공시 문구** — 함께 읽으면 좋은 글 카드 바로 위 (법적 의무):
```html
<p style="font-size:12px;color:#999;margin-top:32px;padding-top:12px;border-top:1px solid #eee;">
이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받을 수 있습니다.
</p>
```

### 주의사항
- `rel="nofollow sponsored"` 속성 필수 — Google 유료 링크 가이드라인
- 공시 문구는 포스트 내 1회만 삽입 (법적 의무: 표시·광고의 공정화에 관한 법률)
- 링크가 없으면 CTA·공시 문구 모두 삽입하지 않음
- `04_notion_upload.py` 수정 불필요 — HTML 블록은 마크다운 변환 시 그대로 통과됨

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

### [04_notion_upload.py] HTML 태그 중간 분할 → Tistory 렌더링 오류

**문제**: `make_paragraph_blocks()`가 1,900자 단위로 기계적으로 분할할 때 HTML 태그 중간을 자르면,
`</div>` → `</di` + `\n` + `v>` 로 분리됨. Notion 블록을 `"\n".join(texts)` 로 합치면 `</di\nv>` 가 되고,
Tistory 에디터에서 브라우저가 줄바꿈을 공백으로 처리해 `</di v>` 가 텍스트로 그대로 노출됨.

**증상**: 게시글 하단 "함께 읽으면 좋은 글" 카드 내부에 `</di v>` 같은 깨진 태그가 텍스트로 보임.

**해결** (`04_notion_upload.py:make_paragraph_blocks()`):
```python
# CHUNK_SIZE(1900) 이내에서 마지막 '>' 위치를 찾아 그 이후에서 분할
safe_end = html.rfind('>', pos, end + 1)
if safe_end == -1 or safe_end <= pos:
    chunk = html[pos:end]   # '>' 없으면 그냥 자름 (순수 텍스트 구간)
else:
    chunk = html[pos:safe_end + 1]
    pos = safe_end + 1
```

**재발 방지**: 이 함수를 수정할 때 반드시 태그 경계('>') 기준 분할 로직을 유지할 것.
CHUNK_SIZE 변경 시에도 동일한 방식으로 유지.

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

### [blog-writer] THUMBNAIL_PROMPT 블록 — 본문 노출 방지

**문제**: blog-writer가 대표 이미지 프롬프트를 `[THUMBNAIL_PROMPT]...[/THUMBNAIL_PROMPT]` 형식으로 마크다운 파일 끝에 삽입하면, `04_notion_upload.py`의 마크다운→HTML 변환 시 이 블록이 그대로 본문에 포함되어 Tistory 게시글 하단에 프롬프트 텍스트가 노출됨.

**해결** (`04_notion_upload.py`의 `parse_blog_post()`):
```python
# H1·메타 블록쿼트 제거 후 추가로 프롬프트 블록 제거
body = re.sub(r'\[THUMBNAIL_PROMPT\].*?\[/THUMBNAIL_PROMPT\]', '', body, flags=re.DOTALL)
body = body.strip()
```

**blog-writer 규칙** (blog-writer.md에 명시):
- `[THUMBNAIL_PROMPT]` 블록은 파일 **맨 끝에만** 삽입한다.
- 본문 중간에 절대 넣지 않는다.
- 이 블록은 업로드 시 자동 제거되므로 독자에게 노출되지 않는다.

**재발 방지**: `04_notion_upload.py`가 자동 제거하므로 위치를 잘못 지정해도 본문에 노출되지 않음. 단, blog-writer는 반드시 파일 끝에 배치할 것.

---

### [비용 정책] DALL-E 이미지 생성 최소화

**원칙**: gpt-image-1 API는 대표이미지(썸네일) 1장만 생성한다. 본문 이미지는 Pexels 무료 API만 사용하고, Pexels 키가 없거나 검색 실패 시 이미지를 생략한다.

**글 1개당 API 호출 횟수**:
- `04_notion_upload.py`: Pexels 키 있으면 최대 2회(무료), 없으면 0회
- `03_tistory_playwright.py`: 대표이미지 1회 (신규 발행 시만, 재발행 시 캐시 재사용)

**DALL-E 본문 이미지 비활성화** (`04_notion_upload.py`):
```python
# replace_image_placeholders() — DALL-E 폴백 제거
url = _fetch_pexels(description)   # Pexels만 시도
if url:
    return <img 태그>
return ""  # Pexels 없으면 플레이스홀더 제거 (DALL-E 호출 없음)
```

**대표이미지 캐싱** (`03_tistory_playwright.py`):
- `_thumbs/thumb_{page_id[:16]}.png` 에 저장
- 동일 page_id 재발행 시 기존 파일 재사용 (DALL-E 호출 없음)

**비용 확인**: https://platform.openai.com/usage

---

### [Tistory] TinyMCE setContent — f-string embed 금지

**문제**: HTML을 Python f-string으로 JavaScript 템플릿 리터럴에 직접 embed하면 HTML 내 `${}`, `{`, `}`, 백틱 등 특수문자 충돌로 `setContent`가 부분 삽입되거나 무시됨. 발행 패널 "공개 발행" 클릭 후 패널이 닫히지 않고 포스트가 저장되지 않는 무증상 실패 발생.

**잘못된 코드**:
```python
escaped = html_content.replace("\\", "\\\\").replace("`", "\\`")
page.evaluate(f'() => {{ tinymce.activeEditor.setContent(`{escaped}`) }}')
```

**올바른 코드** — HTML을 JS 인자로 전달 + `fire('change')` + `save()` 필수:
```python
page.evaluate("""
    (html) => {
        tinymce.activeEditor.setContent(html);
        tinymce.activeEditor.fire('change');  # Tistory에 변경 알림
        tinymce.activeEditor.save();          # 내부 textarea 동기화
    }
""", html_content)
```

**`fire('change')` + `save()` 생략 시 증상**: `setContent`는 시각적으로는 반영되지만, Tistory 발행 시 기존 저장 내용이 제출되어 변경 사항이 무시된다. 로그에는 ✅ 표시되지만 실제 페이지는 변경 전 상태로 유지됨.

**증상 패턴**: `✅ 본문 입력 완료 (방식: tinymce)` + `✅ 발행 완료` 로그가 정상 출력되지만, 실제 Tistory URL이 404를 반환함. `debug_after_publish.png`에 발행 패널이 열린 채로 남아있음.

---

### [Tistory] 대표이미지 — 재발행 시 재생성 금지

**문제**: `03_tistory_playwright.py`가 매 실행마다 DALL-E로 새 썸네일을 생성함. 재발행/재시도 시 불필요한 API 비용 발생 + 포스트마다 썸네일이 달라짐.

**해결**: `page_id` 기반 파일명으로 `_thumbs/` 디렉토리에 캐싱:
```python
# 캐시 확인
thumb_path = get_cached_thumbnail(page_id)  # _thumbs/thumb_{page_id[:16]}.png
if thumb_path:
    print("기존 썸네일 재사용")
elif OPENAI_KEY:
    b64 = generate_thumbnail_base64(title)
    thumb_path = save_thumbnail_temp(b64, page_id)  # page_id로 저장
```

**규칙**:
- 발행 성공/실패 여부와 무관하게 `_thumbs/` 파일은 삭제하지 않음
- 동일 Notion page_id로 재발행 시 자동으로 기존 썸네일 사용
- `_thumbs/` 디렉토리를 `.gitignore`에 추가할 것 (바이너리 파일)

---

### [파이프라인] 이전 세션 02_blog_post.md 잔존 → 잘못된 포스트 발행

**문제**: 이전 세션에서 작성한 `02_blog_post.md`가 파일로 남아있는 상태에서 새 세션이 시작됨. 사용자가 새 포스트를 작성하기 전에 `04_notion_upload.py`를 실행하면 이전 세션 내용이 Notion에 올라가고 Tistory에 발행됨.

**증상**: Tistory에 의도한 글이 아닌 이전 세션 글이 발행됨. 제목만 봐서는 확인이 어려울 수 있음.

**예방 규칙**:
1. **blog-writer는 작성 완료 후 반드시 다음 메시지를 출력한다**:
   ```
   ✅ 발행 준비 완료
   제목: [H1 제목]
   파이프라인: python -X utf8 04_notion_upload.py → python -X utf8 03_tistory_playwright.py
   ```
2. `04_notion_upload.py` 실행 시 제목이 의도한 포스트와 다르면 Ctrl+C로 중단하고 `02_blog_post.md`를 확인한다.
3. 이전 세션 파일 덮어쓰기 전 확인: `head -n 3 _workspace/02_blog_post.md`

**발생 시 대응**: Tistory 잘못 발행 → 아래 "[Tistory] 포스트 삭제" 절차 참조.

---

### [04_notion_upload.py] 카테고리 자동 분류 — 마크다운 메타 우선 사용

**문제**: `detect_category(title)`가 제목 키워드만 보고 분류. "국민성장펀드" 제목에서 "펀드" 키워드가 `주식ETF` 규칙에 매칭되어 잘못 분류됨.

**근본 원인**: 
- `CATEGORY_RULES`에 `"펀드"` 키워드가 `주식ETF` 규칙에 포함됨 (너무 광범위)
- blog-writer가 마크다운에 명시한 `> **카테고리**: 절세연금`을 무시했음

**해결 (코드 수정 완료)**:
1. `parse_blog_post()`가 블록쿼트 제거 전에 `> **카테고리**:` 와 `> **태그**:` 를 먼저 추출
2. 추출된 값이 있으면 `detect_category()`/`extract_tags()` 대신 우선 사용:
   ```python
   category = meta_category or detect_category(title)
   tags = meta_tags if meta_tags else extract_tags(title)
   ```
3. `CATEGORY_RULES`에서 `"펀드"` → `"공모펀드", "주식형펀드", "채권형펀드"` 로 교체

**blog-writer 준수 사항**: 마크다운 메타 블록쿼트에 반드시 다음 형식으로 카테고리·태그 명시:
```
> **카테고리**: 절세연금
> **태그**: 태그1, 태그2, 태그3, ...
```
이 값이 Notion에 그대로 저장되므로 정확한 카테고리명(절세연금/주식ETF/대출금리/…)을 사용할 것.

---

### [Tistory] 포스트 삭제 — Playwright 자동화

**DOM 구조** (manage/posts 목록):
```html
<li>
  <div class="post_btn">
    <div class="info_btn">
      <a class="btn_post" href="/manage/post/{id}?...">수정</a>
      <a class="btn_post" href="#">삭제</a>   ← 이 버튼
      <a class="btn_post" href="/manage/statistics/...">통계</a>
    </div>
  </div>
</li>
```

**삭제 확인**: native `window.confirm` ("선택한 글을 삭제하시겠습니까?") — React 모달 아님.

**핵심**: `page.on("dialog", ...)` 핸들러를 반드시 **클릭 전에** 등록해야 함.

**올바른 코드**:
```python
# 1) dialog 핸들러 먼저 등록
page.on("dialog", lambda d: d.accept())

# 2) 특정 포스트 행의 삭제 버튼 JS로 클릭
page.evaluate("""
    () => {
        const editLinks = document.querySelectorAll('a.btn_post[href*="/manage/post/67"]');
        if (!editLinks.length) return false;
        const row = editLinks[0].closest('li');
        const delBtn = row.querySelector('a.btn_post[href="#"]');
        if (delBtn) { delBtn.click(); return true; }
        return false;
    }
""")
page.wait_for_timeout(2500)
```

**삭제 후 확인**: `requests.get(f"https://{BLOG}.tistory.com/{POST_ID}")` → 404이면 성공.

**주의**: 첫 번째 스크립트에서 `page.on("dialog", ...)` 등록 후 `input()` 호출로 비인터랙티브 환경에서 EOFError 발생 시 dialog가 처리되지 않고 스크립트가 종료된다. `input()` 제거하거나 `headless=False`로 실행할 것.

---

### [내부 링크 카드] 썸네일 URL 만료 — 약 1개월 주기로 전체 깨짐 (2026-08-03 근본 해결됨)

> ✅ **2026-08-03부터 이 문제는 구조적으로 해결됨**: `thumb_host.py` 도입 이후 썸네일을
> `assets/thumbnails/`에 영구 커밋하고 jsdelivr CDN으로 서빙한다 — 더 이상 만료되지 않는다.
> 아래는 문제가 왜 반복됐는지, 어떻게 고쳤는지 기록해 둔 이력이다. 새 포스트는 위
> "인덱스 썸네일 업데이트 — 발행 후 즉시 수행 (영구 호스팅)" 섹션을 따를 것 —
> `refresh_thumbs.py`/`update_posts.py` 대량 재발행은 더 이상 정기적으로 필요하지 않다.

**문제(이력)**: `_posts_index.md`의 `thumb` 필드는 Tistory og:image 프록시(`img1.daumcdn.net/thumb/...`) URL을 저장하는데, 이 URL은 내부에 `credential`·`expires`·`signature` 서명이 걸려 있고 **발급 후 약 1개월이면 만료**된다. 만료되면 원본 `blog.kakaocdn.net` 이미지가 404를 반환해 "함께 읽으면 좋은 글" 카드 이미지가 전부 깨진다.

**증상**: 특정 시점 이후 발행된 모든 포스트의 내부 링크 카드 썸네일이 동시에 깨짐(예: 2026-07-16 점검 시 인덱스 102개 항목 전부가 `expires=1782831599`, 즉 2026-06-30 만료로 통일되어 있었음 — 최초 수집 시점이 몰려 있어 한꺼번에 터짐).

**해결**: 만료된 thumb URL은 **재수집(get_og.py 패턴)하면 항상 새로 서명된 URL을 받을 수 있다** — Tistory가 요청 시점 기준 새 서명을 발급하기 때문. 고정 불변 URL이 아니므로:
1. `_posts_index.md`의 thumb 값은 "한 번 저장하면 끝"이 아니라 **주기적으로 재검증·재수집이 필요한 캐시**로 취급한다.
2. 이미 발행된 포스트 본문 안에 박제된 카드 이미지도 같은 이유로 시간이 지나면 깨진다 — 새 포스트 작성 시뿐 아니라, 기존 포스트를 재발행할 계기가 있으면 카드 이미지도 함께 새로고침을 검토한다.
3. 슬러그(entry/제목) URL 포스트는 공개 URL만으로 편집 페이지(`/manage/post/{id}`)에 접근할 수 없다 — 페이지 소스의 `"entryId":숫자` 값이 실제 내부 게시글 ID이므로 이를 추출해 사용한다.

**징후 감지법**:
```python
# thumb URL의 expires 파라미터를 확인해 만료 여부 판단
import re, datetime
m = re.search(r'expires%3D(\d+)|expires=(\d+)', thumb_url)
expires_at = datetime.datetime.utcfromtimestamp(int(m.group(1) or m.group(2)))
is_expired = expires_at < datetime.datetime.utcnow()
```

**재발 방지 — `refresh_thumbs.py` (프로젝트 루트)**:
```bash
python -X utf8 refresh_thumbs.py --check   # 만료 현황만 리포트 (파일 변경 없음)
python -X utf8 refresh_thumbs.py           # 인덱스 thumb 전체 재수집 + 깨진 카드 patch 파일(enhanced_{id}.html) 생성
python -X utf8 update_posts.py             # 위 patch 파일을 UPDATE_POSTS에 반영 후 실제 라이브 재발행
```
- **새 포스트 작성 시작 전** `--check` 로 만료 임박 항목이 있는지 확인하는 습관을 들일 것 — 특히 대량 발행 배치(예: 애드센스 소급 개선) 직전·직후.
- `refresh_thumbs.py`(인자 없이 실행)는 파일 변경까지 수행하므로, 실행 후 `update_posts.py`의 `UPDATE_POSTS` 리스트를 출력된 ID로 **정확히 교체**한 뒤 실행할 것.
- `update_posts.py`는 2026-07-16부터 **발행 성공 시 해당 `enhanced_{id}.html`을 자동 삭제**한다 — 과거 세션의 잔존 patch 파일이 다음 실행에 섞여 의도치 않은 포스트가 재발행되는 사고(2026-07-16 실제 발견)를 막기 위함. 실패한 포스트의 파일만 재시도용으로 남는다.

---

### [04_notion_upload.py] parse_blog_post() 블록쿼트 처리 — 두 번 회귀했던 지점

**문제 이력** (2026-07-17 하루 동안 순서대로 발견):
1. 원래 `body = re.sub(r'^>.*\n?', '', body, ...)`로 **모든** 블록쿼트를 지웠음 — 카테고리·태그 메타뿐 아니라 "최종 업데이트" 공지와 면책 문구까지 통째로 삭제됨. 프로젝트 최초 커밋부터 있던 버그라 금융 카테고리 92개 중 83개에서 발견됨.
2. 1차 수정 시 `> **카테고리**:`, `> **태그**:` 두 줄만 화이트리스트에 넣었는데, blog-writer.md "산출물 포맷"이 실제로 emit하는 메타 필드는 5개(메타 디스크립션·키워드·예상 읽기 시간·카테고리·태그)라서 나머지 3개가 본문에 그대로 노출됨.

**해결**: `META_ONLY_LABELS` 리스트로 5개 필드를 전부 화이트리스트 처리(`04_notion_upload.py:parse_blog_post()`). 이 5개 외의 블록쿼트(최종 업데이트 공지, 면책 문구 등)는 절대 건드리지 않는다 — "제거 대상은 위치가 아니라 라벨로 판별"하는 원칙을 지킬 것. 같은 실수를 막기 위해 `python -X utf8 04_notion_upload.py --selftest`에 회귀 테스트 고정.

**재발 방지**: 이 함수의 정규식을 손댈 때마다 `--selftest`를 반드시 실행할 것. 테스트는 메타 5개 필드 제거·공지/면책 블록쿼트 보존·카테고리 쉼표 정규화를 한 번에 검증한다.

---

### [04_notion_upload.py] 카테고리 쉼표 자동 정규화

**문제**: blog-writer가 `> **카테고리**: 절세, 연금`처럼 Tistory 표시명(쉼표 포함) 그대로 쓰면 Notion select 저장 시 `validation_error`(쉼표 불허)로 업로드 자체가 실패한다.

**해결**: `parse_blog_post()`에서 `meta_category` 추출 시 `.replace(", ", "").replace(",", "")`로 자동 정규화 — "절세, 연금" → "절세연금". CATEGORY_RULES의 저장명과 동일한 형태가 되므로 안전하다.

---

### [verify_post.py] 발행 직후 자동 점검 — 신규 공용 모듈

**배경**: 위 두 버그 모두 quality-reviewer가 **소스 마크다운**은 검증했지만 **실제 발행된 라이브 페이지**는 확인하지 않아 오래 방치됐다. "원고에 있으면 발행에도 있다"는 가정이 틀렸다.

**해결**: `verify_post.py`(신규, 프로젝트 루트) — `update_posts.py`와 `03_tistory_playwright.py` 양쪽에서 발행 성공 직후 자동 호출한다. 점검 항목:
- 메타 디스크립션·예상 읽기 시간 등 내부용 필드가 본문에 노출됐는지
- 공지·면책 블록쿼트(`<blockquote`)가 존재하는지
- 내부링크 카드 이미지(`thumb/R800x0`) URL이 실제로 200을 반환하는지
- **URL 슬러그 불일치 자동 복구**: 제목에 쉼표·물음표가 있으면 Tistory가 슬러그 생성 시 해당 문자를 제거해 발행 패널이 보여준 URL과 실제 라이브 URL이 달라진다(SOXL·재산세·부가세 글에서 반복 확인). 최초 URL이 404면 쉼표·물음표를 제거한 URL로 자동 재시도하고, 성공하면 실제 라이브 URL을 콘솔에 출력한다.

발행을 막지는 않는다 — 문제 발견 시 콘솔에 경고만 출력. 사람이 바로 알아채고 다음 배치 전에 고칠 수 있게 하는 것이 목적.

```bash
python -X utf8 -c "from verify_post import print_verify_result; print_verify_result('라벨', 'https://j2gblog.tistory.com/{번호}')"
```

---

### [내부링크 카드] 에이전트가 이미지 해시를 잘못 옮겨 적는 문제

**문제**: blog-writer/에이전트가 `_posts_index.md`의 thumb URL을 "그대로 복사"하라는 지시에도 가끔 이미지 해시(`fname=` 뒤 경로) 일부를 다르게 써서 404가 나는 카드가 섞여 들어간다(2026-07-16, 2026-07-17 각 1건 실측 확인). 사람이 매번 각 카드 이미지를 직접 curl로 확인하지 않으면 놓치기 쉽다.

**재발 방지**: 프롬프트 지시만으로는 100% 막을 수 없음을 전제로, `verify_post.py`의 발행 후 자동 점검이 카드 이미지 상태를 매번 확인한다 — 근본 예방보다 **발행 직후 자동 탐지**로 대응.

---

### [알려진 한계] `_posts_index.md`와 라이브 상태 불일치 — 자동 탐지 도구 없음

2026-07-17 하루 동안 라이브에는 정상 존재하지만 인덱스에 누락된 포스트 2건(`/43`, `/49`), 같은 라이브 글을 가리키는 중복 항목 2건(`/37`, `/49`)을 수작업으로 발견했다. 인덱스 전체를 순회하는 `refresh_thumbs.py`는 "인덱스에 있는 항목이 라이브와 다른가"는 잡지만 "라이브에는 있는데 인덱스에 없는 항목"은 구조적으로 못 잡는다(Tistory 전체 사이트맵 크롤링이 필요해 별도 도구 필요).

**현재 대응**: 자동화 도구 없음 — 새 글 작성 시 언급되는 내부 링크 대상 번호가 인덱스에 없으면(예: 이번 세션의 `/43`, `/49`) 그때그때 라이브에서 직접 확인 후 인덱스에 추가하는 수작업으로 처리 중. 인덱스 무결성이 반복적으로 문제가 되면 그때 사이트맵 기반 크롤러 도입을 검토할 것 — 지금 시점에 선제적으로 만들 정도의 빈도는 아니다.

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
