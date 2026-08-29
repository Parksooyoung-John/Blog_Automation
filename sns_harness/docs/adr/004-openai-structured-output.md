# ADR-004: OpenAI Responses Structured Outputs

- 상태: 승인
- 결정: 기본 `gpt-5.4-mini`, `store=false`, 엄격한 JSON Schema를 사용한다.
- 이유: 짧은 한국어 카피 작업의 비용을 제한하고 형식·게시문 수·길이를 코드로 재검증한다.
- 결과: Writer와 Reviewer는 외부 쓰기 권한이 없고 Pydantic 모델만 반환한다.
