# 디자인 스킬 조합 (2026-10-19 확정)

## 결론

| 용도 | 쓰는 것 | 이유 |
|---|---|---|
| 웹 UI·랜딩 | `hallmark`(생성) → `web-design-guidelines`(감사) | 샘플에서 모바일 줄바꿈·색·폰트 규칙 위반을 구조적으로 막았다 |
| SNS 카드뉴스·썸네일 | 기존 `make_naver_images.py` + Canva MCP 유지 | 이미 정보형 한글 카드 6종·템플릿 파이프라인이 있다. hallmark는 페이지용이라 카드엔 규칙만 빌려 쓴다 |
| 디지털 디자인 파일 | Canva MCP | 변경 없음 |

## 설치한 것 (프로젝트 범위 `.claude/skills/`, 전역 변경 없음)

- `hallmark` — Nutlope/hallmark v1.1.0, MIT. SKILL.md 1개 + references(.md)만. 스크립트·hook·네트워크 호출 없음(패턴 검색으로 확인).
- `web-design-guidelines` — vercel-labs, MIT. 원본은 실행 때마다 원격 규칙을 받아 지시로 쓰는 구조라서, 규칙을 `rules.md`로 **고정 복사**하고 SKILL.md가 로컬만 읽게 고쳤다(외부 텍스트가 지시로 들어오는 경로 차단). 갱신은 수동으로 하고 diff를 본다.
- 기존 스킬 5개(`content-atomization` 등)는 해시 불변.

## 설치하지 않은 것

| 스킬 | 이유 |
|---|---|
| frontend-design | 마켓플레이스 캐시에만 있고 비활성. hallmark와 역할 중복 → 켜지 않음 |
| ui-ux-pro-max | hallmark와 중복, 한글 폰트 미고려, Python 스크립트 실행 필요 |
| emil-design-eng | 모션 전용. 웹 애니메이션 작업이 생길 때 재검토. 라이선스 원문 미확인 |
| canvas-design (Apache-2.0) | 텍스트 최소 포스터 철학 ↔ 정보형 한글 카드와 반대, 번들 폰트에 한글 없음 |
| algorithmic-art | 제너러티브 아트 용도 불일치 |
| brand-guidelines | Anthropic 색·폰트 하드코딩 |
| superpowers (MIT) | 세션 시작 부트스트랩이 전역 CLAUDE.md·ponytail·"서브에이전트 최소화"와 충돌, 디자인 무관 |

## 샘플 비교 (연말정산 카드 공제, 동일 내용)

산출물: `_workspace/design_compare/before|after/` (card 1080², thumb 1280×720, landing 1280 / 375). `_workspace`는 gitignore라 로컬에만 있다. 재생성은 `python _workspace/design_compare/render.py before|after`.

점수 1~5. 평가자는 작성한 Claude 본인이고 샘플은 1세트라서 통계적 근거가 아니라 육안 비교다.

| 기준 | 카드 전→후 | 썸네일 전→후 | 랜딩(375px) 전→후 |
|---|---|---|---|
| 시각적 완성도 | 2→4 | 3→4 | 2→4 |
| 한글 가독성 | 4→5 | 4→5 | 2→5 |
| 색·폰트 일관성 | 2→4 | 2→4 | 2→5 |
| 모바일 최적화 | 3→4 | 3→4 | 2→5 |
| 정보 전달력 | 3→5 | 2→4 | 3→5 |

근거(관찰한 것):
- 전: 보라 그라디언트 + 이모지(🚀), 카드 4개가 같은 무게, 한도를 "300~400만원"으로 뭉갬. 모바일 랜딩에서 "카/드", "한눈/에"처럼 어절 중간에서 줄이 끊김(`word-break: keep-all` 없음).
- 후: 토큰 고정(`tokens.css`, OKLCH, 단일 강조색 1개), 이모지·그라디언트 없음, `keep-all`, 핵심 수치(30%) 하나만 강조, 모바일 가로 스크롤 없음(scrollWidth = viewport 확인).
- 후 카드는 첫 렌더에서 푸터가 캔버스 밖으로 잘렸고(전엔 없던 문제) 여백을 줄여 고쳤다.
- 표시용 글꼴(Gmarket Sans)은 헤드리스 Chromium에서 적용되지 않아 Noto Sans KR로 대체됐다. 후 결과는 Noto 단일 글꼴 기준이다.

제작 소요(도구 호출 포함 실측): 전 28초, 후 63초(규칙 읽기 포함). 후는 약 2배 걸렸고, 규칙을 읽는 비용(SKILL.md 68KB + references)은 매번 든다.

## 한계 (그대로 믿지 말 것)

- 카드·썸네일의 개선 중 상당 부분은 hallmark 고유 기능이 아니라 "이모지·그라디언트 빼고 토큰·`keep-all` 지킨다"는 규칙에서 나왔다. 같은 규칙을 `make_naver_images.py`에 직접 넣어도 비슷한 효과가 난다. hallmark의 실질 이득은 웹 페이지(구조 다양성·모바일 게이트)에서 나온다.
- 점수는 같은 세션이 만든 결과를 스스로 평가한 것이다. 실제 선택은 사용자가 두 PNG를 직접 보고 하는 것이 맞다.

## 사용법

- 웹 UI: "hallmark로 <내용> 랜딩 만들어줘" → 끝나면 "web-design-guidelines로 <파일> 검토". 기존 사이트는 `hallmark audit <파일>`(수정 없이 점검) 먼저.
- 카드·썸네일: `python -X utf8 make_naver_images.py --card 이름 | --thumb NN` 그대로. 새 카드 형태를 만들 때만 `_workspace/design_compare/after/tokens.css`의 색·간격 토큰과 `word-break: keep-all`을 참고한다.
- 보류: 돈살림표 전용 브랜드 스킬(`brand-donsalimpyo`). 카드 파이프라인 색을 토큰으로 정리할 때 같이 만든다.
