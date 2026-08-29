# Agent 구조와 역할

## Orchestrator

결정적인 Python 코드로 상태 전이와 실행 순서를 통제한다. LLM 응답을 신뢰하지 않고 Pydantic
계약과 코드 검사를 통과시킨다. 외부 쓰기는 Queue와 Publisher 어댑터에만 위임한다.

## Source Agent

RSS를 우선하고 홈 목록을 폴백으로 사용한다. 숫자형 canonical URL만 받아 JSON-LD·OG·본문·
태그·발행일을 `SourcePost`로 정규화한다.

## Threads Writer

OpenAI Responses API Structured Outputs로 `single` 또는 `thread`를 선택한다. 원문 밖 지식과
숫자를 만들 수 없고 링크 배치·분량 계약을 지킨다.

## Compliance Reviewer

원문과 초안을 다시 비교한다. 코드가 탐지한 신규 숫자·금지 문구·링크 오류를 수정하며,
수정할 수 없는 경우 `보류` 사유를 반환한다.

## Scheduler / Publisher

승인된 빈 슬롯을 KST 08:30·18:30에 배정한다. 게시 직전 상태를 `게시중`으로 바꾸고 공식
Threads API 결과 ID를 게시문마다 저장한다. LLM을 호출하지 않는다.
